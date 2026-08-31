"""
gui/views/node_config_panel.py
--------------------------------
Right-side scroll panel showing editable configuration for the
currently selected pipeline node with typed parameter widgets and
real-time validation.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Callable

try:
    from PyQt6.QtCore import Qt  # type: ignore
    from PyQt6.QtGui import QFont  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QScrollArea, QWidget, QFormLayout, QLabel,
        QLineEdit, QFrame, QHBoxLayout, QPushButton,
        QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox,
        QFileDialog,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import Colors


def parse_value(s: str) -> Any:
    """Parse a configuration string back to its appropriate Python type."""
    if not isinstance(s, str):
        return s
    s = s.strip()
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.lower() in ("none", "null", ""):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    try:
        return json.loads(s.replace("'", '"'))
    except Exception:
        pass
    return s


class NodeConfigPanel(QScrollArea):
    """Right-side panel that shows editable config for the selected node."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._inner = QWidget()
        self._layout = QFormLayout(self._inner)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)
        self.setWidget(self._inner)
        self._node_id: Optional[str] = None
        self._function_name: str = ""
        self._widgets: Dict[str, QWidget] = {}
        self._getters: Dict[str, Callable[[], Any]] = {}
        self._on_change: Optional[Callable[[dict], None]] = None
        # Store references for theme refresh
        self._separators: list = []
        self._cfg_label: Optional[QLabel] = None
        self._add_label: Optional[QLabel] = None
        self._show_empty()

    def _show_empty(self):
        self._clear()
        lbl = QLabel("Select a node to configure it")
        lbl.setProperty("muted", "true")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addRow(lbl)

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                child_lay = item.layout()
                while child_lay.count():
                    child_item = child_lay.takeAt(0)
                    if child_item.widget():
                        child_item.widget().deleteLater()
                child_lay.deleteLater()
        self._widgets.clear()
        self._getters.clear()
        self._separators.clear()
        self._cfg_label = None
        self._add_label = None

    def _create_typed_widget(self, key: str, val: Any) -> tuple[QWidget, Callable[[], Any]]:
        """Factory for typed parameter widgets based on type/name heuristics."""
        key_lower = key.lower()

        # Bool fields -> QCheckBox
        if isinstance(val, bool):
            cb = QCheckBox()
            cb.setChecked(val)
            cb.toggled.connect(self._handle_change)
            return cb, lambda: cb.isChecked()

        # Int fields -> QSpinBox
        if isinstance(val, int) and not isinstance(val, bool):
            sb = QSpinBox()
            sb.setRange(-999999, 999999)
            sb.setValue(val)
            sb.valueChanged.connect(self._handle_change)
            return sb, lambda: sb.value()

        # Float fields -> QDoubleSpinBox
        if isinstance(val, float):
            dsb = QDoubleSpinBox()
            dsb.setRange(-999999.0, 999999.0)
            dsb.setDecimals(4)
            dsb.setValue(val)
            dsb.valueChanged.connect(self._handle_change)
            return dsb, lambda: dsb.value()

        # Enum/Literal or Options list -> QComboBox
        if isinstance(val, list):
            combo = QComboBox()
            for opt in val:
                combo.addItem(str(opt))
            combo.currentIndexChanged.connect(self._handle_change)
            return combo, lambda: combo.currentText()

        # Path/File strings -> QLineEdit + Browse button
        if any(token in key_lower for token in ("path", "file", "dir")):
            wrapper = QWidget()
            hlay = QHBoxLayout(wrapper)
            hlay.setContentsMargins(0, 0, 0, 0)
            line = QLineEdit(str(val) if val is not None else "")
            line.setPlaceholderText(f"Path to {key}…")
            line.textChanged.connect(self._handle_change)

            btn = QPushButton("Browse")
            def _browse():
                if "dir" in key_lower:
                    path = QFileDialog.getExistingDirectory(self, f"Select {key}")
                else:
                    path, _ = QFileDialog.getOpenFileName(self, f"Select {key}")
                if path:
                    line.setText(path)
            btn.clicked.connect(_browse)

            hlay.addWidget(line)
            hlay.addWidget(btn)
            return wrapper, lambda: line.text()

        # Default string QLineEdit with real-time type validation
        line = QLineEdit(str(val) if val is not None else "")
        line.setPlaceholderText(f"{key}…")

        def _validate_line():
            txt = line.text().strip()
            # If original value was float or int, check type coercion
            if isinstance(val, float):
                try:
                    float(txt)
                    line.setStyleSheet("")
                    line.setToolTip("")
                except ValueError:
                    line.setStyleSheet("border: 1px solid #ef4444;")
                    line.setToolTip("Expected: float")
            elif isinstance(val, int) and not isinstance(val, bool):
                try:
                    int(txt)
                    line.setStyleSheet("")
                    line.setToolTip("")
                except ValueError:
                    line.setStyleSheet("border: 1px solid #ef4444;")
                    line.setToolTip("Expected: integer")

        line.textChanged.connect(lambda: (_validate_line(), self._handle_change()))
        line.editingFinished.connect(_validate_line)
        return line, lambda: parse_value(line.text())

    def load_node(
        self,
        node_id: str,
        function_name: str,
        config: dict,
        on_change: Optional[Callable[[dict], None]] = None,
    ):
        """Populate the panel with typed config fields for the given node."""
        self._clear()
        self._node_id = node_id
        self._function_name = function_name
        self._on_change = on_change

        # Header
        hdr = QLabel(f"⚙  {node_id}")
        hdr.setProperty("heading", "true")
        hdr.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._layout.addRow(hdr)

        sub = QLabel(f"Function: {function_name}")
        sub.setProperty("muted", "true")
        self._layout.addRow(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        self._layout.addRow(sep)
        self._separators.append(sep)

        self._cfg_label = QLabel("Configuration")
        self._layout.addRow(self._cfg_label)

        # Existing keys
        for key, val in config.items():
            widget, getter = self._create_typed_widget(key, val)
            self._layout.addRow(QLabel(key + ":"), widget)
            self._widgets[key] = widget
            self._getters[key] = getter

        if not config:
            no_cfg = QLabel("No parameters set")
            no_cfg.setProperty("muted", "true")
            self._layout.addRow(no_cfg)

        # "Add Parameter" section
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        self._layout.addRow(sep2)
        self._separators.append(sep2)

        self._add_label = QLabel("➕ Add Parameter")
        self._layout.addRow(self._add_label)

        self._new_key_input = QLineEdit()
        self._new_key_input.setPlaceholderText("Parameter name")
        self._new_val_input = QLineEdit()
        self._new_val_input.setPlaceholderText("Value (e.g. 18, true, text)")

        add_lay = QHBoxLayout()
        add_lay.addWidget(self._new_key_input)
        add_lay.addWidget(self._new_val_input)
        self._layout.addRow(add_lay)

        add_btn = QPushButton("Add Parameter")
        add_btn.clicked.connect(self._add_parameter)
        self._layout.addRow(add_btn)

        # Apply theme-aware styles
        self._apply_theme_styles()

    def _apply_theme_styles(self):
        """Apply/re-apply inline styles using current Colors values."""
        sep_style = f"QFrame {{ color: {Colors.BORDER}; }}"
        for sep in self._separators:
            sep.setStyleSheet(sep_style)

        if self._cfg_label:
            self._cfg_label.setStyleSheet(
                f"color: {Colors.DARK_PURPLE}; font-weight: 600; margin-top: 8px;"
            )
        if self._add_label:
            self._add_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-weight: bold; margin-top: 4px;"
            )

    def _handle_change(self):
        if self._on_change:
            cfg = self.get_config()
            self._on_change(cfg)

    def _add_parameter(self):
        key = self._new_key_input.text().strip()
        val = self._new_val_input.text().strip()
        if not key:
            return

        parsed_val = parse_value(val)
        current_config = self.get_config()
        current_config[key] = parsed_val

        if self._on_change:
            self._on_change(current_config)

        self.load_node(
            self._node_id, self._function_name, current_config, self._on_change
        )

    def get_config(self) -> dict:
        """Return the current config values from the form widgets."""
        return {k: getter() for k, getter in self._getters.items()}
