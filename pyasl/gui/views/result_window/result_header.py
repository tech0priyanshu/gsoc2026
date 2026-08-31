"""
gui/views/result_window/result_header.py
------------------------------------------
Header bar for the Result Window.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QWidget, QHBoxLayout, QLabel, QPushButton, QMenu,
        QLineEdit, QInputDialog, QFileDialog,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ResultHeader(QWidget):
    """
    Header bar displaying result name, source, and action buttons.

    Large viewport:  Result Name    Source: ...    [Save] [Export] [⋮]
    Compact viewport: Result Name   [⋮]
    """

    save_requested = pyqtSignal()
    save_as_requested = pyqtSignal(str)
    export_requested = pyqtSignal(str, str, str)  # format, path, export_type

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(Spacing.MD)

        # Result name
        self._name_lbl = QLabel("Untitled Result")
        self._name_lbl.setFont(QFont("Segoe UI", DesignTokens.FONT_SIZE_XL, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; background: transparent;")
        layout.addWidget(self._name_lbl)

        # Source label
        self._source_lbl = QLabel("")
        self._source_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {DesignTokens.FONT_SIZE_SM}px; background: transparent;"
        )
        layout.addWidget(self._source_lbl)

        layout.addStretch()

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("result_save_btn")
        self._save_btn.setToolTip("Save result (Ctrl+S)")
        self._save_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._save_btn.clicked.connect(self.save_requested.emit)
        layout.addWidget(self._save_btn)

        # Export button
        self._export_btn = QPushButton("Export")
        self._export_btn.setObjectName("result_export_btn")
        self._export_btn.setToolTip("Export result data")
        self._export_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._export_btn.clicked.connect(self._show_export_menu)
        layout.addWidget(self._export_btn)

        # More menu
        self._more_btn = QPushButton("⋮")
        self._more_btn.setObjectName("result_more_btn")
        self._more_btn.setFixedSize(DesignTokens.TOOLBAR_BTN_HEIGHT, DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._more_btn.setToolTip("More actions")
        self._more_btn.clicked.connect(self._show_more_menu)
        layout.addWidget(self._more_btn)

        self._apply_theme_styles()

    def refresh(self):
        """Refresh header with current result data."""
        result = self._service.current_result
        if result:
            self._name_lbl.setText(result.name)
            source = result.source_reference
            if source:
                import os
                display = os.path.basename(source) or source
                self._source_lbl.setText(f"Source: {display}")
                self._source_lbl.setToolTip(source)
            else:
                self._source_lbl.setText("")
        else:
            self._name_lbl.setText("No Result")
            self._source_lbl.setText("")

    def _show_export_menu(self):
        """Show the export format menu."""
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style())

        # Current view exports
        menu.addAction("Export Current View → CSV").triggered.connect(
            lambda: self._do_export("csv", "current")
        )
        menu.addAction("Export Current View → JSON").triggered.connect(
            lambda: self._do_export("json", "current")
        )
        menu.addAction("Export Current View → Excel").triggered.connect(
            lambda: self._do_export("xlsx", "current")
        )

        menu.addSeparator()

        # Full result exports
        menu.addAction("Export Full Result → CSV").triggered.connect(
            lambda: self._do_export("csv", "full")
        )
        menu.addAction("Export Full Result → JSON").triggered.connect(
            lambda: self._do_export("json", "full")
        )
        menu.addAction("Export Full Result → Excel").triggered.connect(
            lambda: self._do_export("xlsx", "full")
        )

        menu.addSeparator()

        # PDF report
        menu.addAction("Generate PDF Report").triggered.connect(
            lambda: self._do_export("pdf", "pdf")
        )

        menu.exec(self._export_btn.mapToGlobal(self._export_btn.rect().bottomLeft()))

    def _show_more_menu(self):
        """Show additional actions menu."""
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style())

        # Save As
        save_as = menu.addAction("Save As...")
        save_as.triggered.connect(self._do_save_as)

        menu.addSeparator()

        # Rename
        rename = menu.addAction("Rename Result")
        rename.triggered.connect(self._do_rename)

        menu.exec(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))

    def _do_export(self, fmt: str, export_type: str):
        """Prompt for file path and emit export signal."""
        filter_map = {
            "csv": "CSV Files (*.csv)",
            "json": "JSON Files (*.json)",
            "xlsx": "Excel Files (*.xlsx)",
            "pdf": "PDF Files (*.pdf)",
        }
        file_filter = filter_map.get(fmt, "All Files (*)")
        result_name = self._service.current_result.name if self._service.current_result else "result"
        default_name = f"{result_name.replace(' ', '_')}.{fmt}"

        path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {fmt.upper()}", default_name, file_filter
        )
        if path:
            self.export_requested.emit(fmt, path, export_type)

    def _do_save_as(self):
        """Prompt for a new name and emit save_as signal."""
        current = self._service.current_result
        default = current.name if current else "Result"

        name, ok = QInputDialog.getText(
            self, "Save As", "Enter result name:", QLineEdit.EchoMode.Normal, default
        )
        if ok and name.strip():
            self.save_as_requested.emit(name.strip())

    def _do_rename(self):
        """Rename the current result."""
        current = self._service.current_result
        if not current:
            return

        name, ok = QInputDialog.getText(
            self, "Rename Result", "New name:", QLineEdit.EchoMode.Normal, current.name
        )
        if ok and name.strip():
            current.name = name.strip()
            self.refresh()

    def _menu_style(self) -> str:
        return f"""
            QMenu {{
                background-color: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                color: {Colors.TEXT_PRIMARY};
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.BG_HOVER};
            }}
        """

    def _apply_theme_styles(self):
        self.setStyleSheet(f"""
            ResultHeader {{
                background: {Colors.BG_PANEL};
                border: 1px solid {Colors.BORDER};
                border-radius: {DesignTokens.BORDER_RADIUS_MD}px;
            }}
        """)
