"""
gui/views/pipeline_builder_view.py
------------------------------------
Pipeline Builder tab view.

Layout: [Palette | Canvas | Config Panel]

All business logic (YAML I/O, validate, run) is delegated to
``PipelineController``; this class is pure UI wiring.
"""
from __future__ import annotations

try:
    from PyQt6.QtCore import Qt, QTimer  # type: ignore
    from PyQt6.QtGui import QFont  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
        QLabel, QPushButton, QListWidget, QListWidgetItem,
        QFileDialog, QMessageBox, QLineEdit,
        QToolBar, QFrame, QSizePolicy,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.controllers.pipeline_controller import PipelineController
from pyasl.gui.views.node_canvas import NodeCanvasView
from pyasl.gui.views.node_config_panel import NodeConfigPanel
from pyasl.gui.constants import Colors, Spacing, DesignTokens


class InlineErrorBanner(QFrame):
    """Inline error banner displayed at the top of the Pipeline Builder canvas."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self.setStyleSheet(
            f"background-color: {Colors.RED_BG}; border: 1px solid {Colors.RED}; "
            f"border-radius: {DesignTokens.BORDER_RADIUS_MD}px; "
            f"padding: {Spacing.XS}px {Spacing.MD}px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)

        self.icon_label = QLabel("⚠️")
        layout.addWidget(self.icon_label)

        self.msg_label = QLabel()
        self.msg_label.setWordWrap(True)
        self.msg_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px;")
        layout.addWidget(self.msg_label, stretch=1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_SECONDARY}; "
            "border: none; font-weight: bold; min-width: 22px; min-height: 22px;"
        )
        close_btn.clicked.connect(self.hide_banner)
        layout.addWidget(close_btn)

    def show_error(self, message: str) -> None:
        self.msg_label.setText(message)
        self.setVisible(True)

    def hide_banner(self) -> None:
        self.setVisible(False)


class PipelineBuilderView(QWidget):
    """
    Full Pipeline Builder tab.

    Receives a ``PipelineController`` and wires all UI actions to it.
    """

    def __init__(self, controller: PipelineController, parent=None):
        super().__init__(parent)
        self._ctrl = controller
        self._all_palette_items: list[str] = []
        self._setup_ui()
        self._wire_signals()
        # Defer palette load so the window appears immediately
        QTimer.singleShot(0, self._ctrl.load_palette)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        # Let the QSS handle visual padding; use zero margins for tight layout
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────
        tb = self._build_toolbar()
        root.addWidget(tb)

        # ── Inline Error Banner ──────────────────────────────────
        self.error_banner = InlineErrorBanner()
        root.addWidget(self.error_banner)

        # ── Main splitter (Palette | Canvas | Config) ────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(3)

        # Left: node palette
        palette_widget = self._build_palette()
        splitter.addWidget(palette_widget)

        # Centre: canvas (stretch = 1 so it absorbs extra space)
        self.canvas = NodeCanvasView(self._ctrl.graph)
        splitter.addWidget(self.canvas)

        # Right: config panel
        self.config_panel = NodeConfigPanel()
        self.config_panel.setMinimumWidth(DesignTokens.CONFIG_WIDTH_MIN)
        self.config_panel.setMaximumWidth(DesignTokens.CONFIG_WIDTH_MAX)
        splitter.addWidget(self.config_panel)

        # Stretch factors: palette=0, canvas=1, config=0
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 700, 260])

        root.addWidget(splitter, stretch=1)

        # ── Status bar ───────────────────────────────────────────
        self._status = QLabel("Ready — drag nodes onto the canvas")
        self._status.setObjectName("pipelineStatus")
        self._status.setProperty("muted", "true")
        root.addWidget(self._status)

        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QToolBar:
        """Build the action toolbar with consistent button sizing."""
        tb = QToolBar()
        tb.setMovable(False)
        tb.setObjectName("pipelineToolbar")

        # ── Action buttons ───────────────────────────────────────
        load_btn = QPushButton("Load YAML")
        load_btn.setToolTip("Load a pipeline from a YAML file")
        load_btn.clicked.connect(self._on_load_yaml)

        save_btn = QPushButton("Save YAML")
        save_btn.setProperty("flat", "true")
        save_btn.setToolTip("Save current pipeline to YAML")
        save_btn.clicked.connect(self._on_save_yaml)

        validate_btn = QPushButton("Validate")
        validate_btn.setProperty("flat", "true")
        validate_btn.clicked.connect(self._on_validate)

        self._run_btn = QPushButton("▶ Run")
        self._run_btn.setProperty("success", "true")
        self._run_btn.clicked.connect(self._on_run)

        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("danger", "true")
        clear_btn.clicked.connect(self._on_clear)

        # Apply consistent height to all action buttons
        btn_h = DesignTokens.TOOLBAR_BTN_HEIGHT
        for w in [load_btn, save_btn, validate_btn, self._run_btn, clear_btn]:
            w.setFixedHeight(btn_h)
            tb.addWidget(w)

        # ── Separator + spacer ───────────────────────────────────
        tb.addSeparator()

        # Breathing room between action buttons and node adder
        spacer = QWidget()
        spacer.setFixedWidth(Spacing.LG)
        spacer.setStyleSheet("background: transparent; border: none;")
        tb.addWidget(spacer)

        # ── Node adder section ───────────────────────────────────
        add_lbl = QLabel("Add node:")
        add_lbl.setProperty("muted", "true")
        add_lbl.setStyleSheet(
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; "
            f"color: {Colors.TEXT_SECONDARY}; padding: 0 {Spacing.XS}px; "
            "background: transparent; border: none;"
        )
        tb.addWidget(add_lbl)

        self._new_id = QLineEdit()
        self._new_id.setPlaceholderText("node_id")
        self._new_id.setFixedWidth(140)
        self._new_id.setFixedHeight(btn_h)
        tb.addWidget(self._new_id)

        # Small gap between inputs
        gap = QWidget()
        gap.setFixedWidth(Spacing.XS)
        gap.setStyleSheet("background: transparent; border: none;")
        tb.addWidget(gap)

        self._new_func = QLineEdit()
        self._new_func.setPlaceholderText("function_name")
        self._new_func.setFixedWidth(200)
        self._new_func.setFixedHeight(btn_h)
        tb.addWidget(self._new_func)

        # Small gap before add button
        gap2 = QWidget()
        gap2.setFixedWidth(Spacing.XS)
        gap2.setStyleSheet("background: transparent; border: none;")
        tb.addWidget(gap2)

        add_btn = QPushButton("+ Add")
        add_btn.setFixedHeight(btn_h)
        add_btn.clicked.connect(self._on_add_node_from_toolbar)
        tb.addWidget(add_btn)

        return tb

    # ------------------------------------------------------------------
    # Function Palette
    # ------------------------------------------------------------------

    def _build_palette(self) -> QWidget:
        """Build the left sidebar function palette with modern search."""
        container = QWidget()
        container.setMinimumWidth(DesignTokens.PALETTE_WIDTH_MIN)
        container.setMaximumWidth(DesignTokens.PALETTE_WIDTH_MAX)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.SM, Spacing.MD)
        lay.setSpacing(Spacing.SM)

        # Header
        header = QLabel("Function Palette")
        header.setObjectName("paletteHeader")
        header.setFont(QFont("Segoe UI", DesignTokens.FONT_SIZE_MD, QFont.Weight.Bold))
        lay.addWidget(header)

        # Search / filter box
        search = QLineEdit()
        search.setObjectName("paletteSearch")
        search.setPlaceholderText("Filter functions...")
        search.setClearButtonEnabled(True)
        search.setFixedHeight(DesignTokens.TOOLBAR_INPUT_HEIGHT)
        search.textChanged.connect(self._on_filter_palette)
        lay.addWidget(search)

        # Function list
        self._palette_list = QListWidget()
        self._palette_list.setObjectName("paletteList")
        self._palette_list.setToolTip(
            "Double-click to add a node with this function to the canvas"
        )
        self._palette_list.itemDoubleClicked.connect(self._on_palette_add)
        # The list should fill all remaining vertical space
        self._palette_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        lay.addWidget(self._palette_list, stretch=1)

        return container

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self):
        # Controller → view
        self._ctrl.palette_loaded.connect(self._populate_palette)
        self._ctrl.graph_changed.connect(self._on_graph_changed)
        self._ctrl.run_started.connect(self._on_run_started)
        self._ctrl.run_completed.connect(self._on_run_completed)
        self._ctrl.error.connect(self._on_error)

        # Canvas → controller
        self.canvas.node_clicked.connect(self._on_node_selected)
        self.canvas.node_connect_requested.connect(self._ctrl.connect_nodes)
        self.canvas.node_remove_requested.connect(self._ctrl.remove_node)
        self.canvas.node_clear_deps_requested.connect(
            self._ctrl.clear_dependencies
        )

    # ------------------------------------------------------------------
    # Palette
    # ------------------------------------------------------------------

    def _populate_palette(self, names: list):
        self._all_palette_items = names
        self._refresh_palette(names)

    def _refresh_palette(self, names: list):
        self._palette_list.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setToolTip(f"Double-click to add '{name}' to the canvas")
            self._palette_list.addItem(item)

    def _on_filter_palette(self, text: str):
        filtered = [
            n for n in self._all_palette_items
            if text.lower() in n.lower()
        ]
        self._refresh_palette(filtered)

    def _on_palette_add(self, item: QListWidgetItem):
        func_name = item.text()
        node_id = self._ctrl.add_node_from_palette(func_name)
        self._status.setText(f"Added node '{node_id}' ({func_name})")
        self.canvas.update()

    # ------------------------------------------------------------------
    # Node interactions
    # ------------------------------------------------------------------

    def _on_add_node_from_toolbar(self):
        nid = self._new_id.text().strip()
        fn = self._new_func.text().strip()
        if not nid or not fn:
            QMessageBox.warning(
                self, "Missing fields",
                "Enter both node_id and function_name.",
            )
            return
        self._ctrl.add_node(nid, fn)
        self._new_id.clear()
        self._new_func.clear()
        self.canvas.update()

    def _on_node_selected(self, node_id: str):
        node = self._ctrl.graph.nodes.get(node_id)
        if node:
            self.config_panel.load_node(
                node_id, node.function_name,
                self._ctrl.state.get_config(node_id),
                lambda cfg: self._ctrl.state.set_config(node_id, cfg),
            )

    def _on_graph_changed(self):
        total = len(self._ctrl.graph.nodes)
        self._status.setText(
            f"{total} node{'s' if total != 1 else ''} on canvas  |  "
            "Ctrl+click two nodes to connect them"
        )
        self.canvas.update()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_load_yaml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Pipeline YAML", "", "YAML Files (*.yaml *.yml)"
        )
        if path:
            self._ctrl.load_yaml(path)
            self.canvas.zoom_fit()



    def _on_clear(self) -> None:
        """Confirmation dialog before clearing the pipeline builder canvas (GUI-3)."""
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear the entire pipeline? This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.error_banner.hide_banner()
            self._ctrl.clear()
            self.canvas.update()

    def _on_save_yaml(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Pipeline YAML", "pipeline.yaml",
            "YAML Files (*.yaml *.yml)",
        )
        if path:
            self._ctrl.save_yaml(path)
            self._status.setText(f"Saved to {path}")

    def _on_validate(self):
        err = self._ctrl.validate()
        if err is None:
            self.error_banner.hide_banner()
            QMessageBox.information(
                self, "Valid",
                "Pipeline graph is valid — no cycles or missing dependencies.",
            )
        elif err == "No nodes on the canvas.":
            self.error_banner.hide_banner()
            QMessageBox.information(self, "Empty", err)
        else:
            self.error_banner.show_error(f"Validation Failed: {err}")

    def _on_run(self):
        self.error_banner.hide_banner()
        self._ctrl.run()
        self.canvas.update()

    def _on_run_started(self):
        self._run_btn.setEnabled(False)
        self._status.setText("Pipeline running…")

    def _on_run_completed(self, text: str):
        self._run_btn.setEnabled(True)
        self._status.setText(text)

    def _on_error(self, msg: str):
        self._run_btn.setEnabled(True)
        self.error_banner.show_error(msg)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme_styles(self):
        """Apply/re-apply all inline styles using current Colors values."""
        self._status.setStyleSheet(
            f"padding: {Spacing.SM}px {Spacing.MD}px; "
            f"color: {Colors.TEXT_SECONDARY}; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; "
            f"border-top: 1px solid {Colors.BORDER}; "
            "background: transparent;"
        )
        # Config panel re-applies its own styles on load_node
        if hasattr(self, 'config_panel'):
            self.config_panel._apply_theme_styles()
