"""
gui/views/result_window/export_menu.py
-----------------------------------------
Unified export menu with all export options.
"""
from __future__ import annotations

import logging
import os

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QWidget, QMenu, QPushButton, QFileDialog, QMessageBox,
    )
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ExportMenu(QWidget):
    """
    Unified export button with a dropdown menu.

    Export ▼
    ├── Export Current View
    │   ├── CSV
    │   ├── JSON
    │   └── Excel
    ├── Export Full Result
    │   ├── CSV
    │   ├── JSON
    │   └── Excel
    ├── PDF Report
    └── Export Chart
        ├── PNG
        ├── SVG
        └── PDF
    """

    export_triggered = pyqtSignal(str, str, str)  # format, path, export_type

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._setup_ui()

    def _setup_ui(self):
        self._btn = QPushButton("Export")
        self._btn.setAccessibleName("Export menu")
        self._btn.setObjectName("export_menu_btn")
        self._btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: 0 {Spacing.MD}px; font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_TERTIARY}; }}"
        )
        self._btn.clicked.connect(self._show_menu)

    def get_button(self) -> QPushButton:
        return self._btn

    def _show_menu(self):
        menu = QMenu(self._btn)
        menu.setStyleSheet(
            f"QMenu {{ background: {Colors.BG_SECONDARY}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 24px; }}"
            f"QMenu::item:selected {{ background: {Colors.BG_TERTIARY}; }}"
        )

        # ── Export Current View ──
        current_menu = menu.addMenu("Export Current View")
        current_menu.addAction("CSV (.csv)", lambda: self._export("csv", "current"))
        current_menu.addAction("JSON (.json)", lambda: self._export("json", "current"))
        current_menu.addAction("Excel (.xlsx)", lambda: self._export("xlsx", "current"))

        # ── Export Full Result ──
        full_menu = menu.addMenu("Export Full Result")
        full_menu.addAction("CSV (.csv)", lambda: self._export("csv", "full"))
        full_menu.addAction("JSON (.json)", lambda: self._export("json", "full"))
        full_menu.addAction("Excel (.xlsx)", lambda: self._export("xlsx", "full"))

        menu.addSeparator()

        # ── PDF Report ──
        menu.addAction("PDF Report", lambda: self._export("pdf", "pdf"))

        # ── Export Chart ──
        chart_menu = menu.addMenu("Export Chart")
        chart_menu.addAction("PNG (.png)", lambda: self._export_chart("png"))
        chart_menu.addAction("SVG (.svg)", lambda: self._export_chart("svg"))
        chart_menu.addAction("PDF (.pdf)", lambda: self._export_chart("pdf"))

        menu.exec(self._btn.mapToGlobal(self._btn.rect().bottomLeft()))

    def _export(self, fmt: str, export_type: str):
        """Prompt user for file path and trigger export."""
        extensions = {
            "csv": "CSV Files (*.csv)",
            "json": "JSON Files (*.json)",
            "xlsx": "Excel Files (*.xlsx)",
            "pdf": "PDF Files (*.pdf)",
        }

        default_name = self._get_default_filename(fmt)

        path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {fmt.upper()}", default_name,
            extensions.get(fmt, "All Files (*)")
        )

        if path:
            self.export_triggered.emit(fmt, path, export_type)

    def _export_chart(self, fmt: str):
        """Export the current chart image."""
        extensions = {
            "png": "PNG Images (*.png)",
            "svg": "SVG Images (*.svg)",
            "pdf": "PDF Files (*.pdf)",
        }

        default_name = f"chart.{fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export Chart as {fmt.upper()}", default_name,
            extensions.get(fmt, "All Files (*)")
        )

        if path:
            self.export_triggered.emit(fmt, path, "chart")

    def _get_default_filename(self, fmt: str) -> str:
        result = self._service.current_result
        name = result.name if result else "result"
        # Sanitize
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        return f"{safe_name}.{fmt}"

    def _apply_theme_styles(self):
        self._btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: 0 {Spacing.MD}px; font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_TERTIARY}; }}"
        )
