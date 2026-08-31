"""
gui/views/result_window/save_controls.py
-------------------------------------------
Save / Save As controls for the result window.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QWidget, QHBoxLayout, QPushButton, QMenu,
        QInputDialog, QMessageBox,
    )
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class SaveControls(QWidget):
    """
    Save button with dropdown for Save As.

    Signals:
        save_requested() — save current result
        save_as_requested(name: str) — save with a new name
    """

    save_requested = pyqtSignal()
    save_as_requested = pyqtSignal(str)

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XS)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setAccessibleName("Save result")
        self._save_btn.setObjectName("save_result_btn")
        self._save_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: white; "
            f"border: none; border-radius: 4px; padding: 0 {Spacing.MD}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_SECONDARY}; }}"
        )
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)

        # More button (Save As)
        self._more_btn = QPushButton("▼")
        self._more_btn.setAccessibleName("More save options")
        self._more_btn.setFixedSize(DesignTokens.TOOLBAR_BTN_HEIGHT, DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._more_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: white; "
            f"border: none; border-radius: 4px; font-size: 10px; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_SECONDARY}; }}"
        )
        self._more_btn.clicked.connect(self._show_more_menu)
        layout.addWidget(self._more_btn)

    def _on_save(self):
        self.save_requested.emit()

    def _show_more_menu(self):
        menu = QMenu(self._more_btn)
        menu.setStyleSheet(
            f"QMenu {{ background: {Colors.BG_SECONDARY}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 24px; }}"
            f"QMenu::item:selected {{ background: {Colors.BG_TERTIARY}; }}"
        )
        menu.addAction("Save As…", self._on_save_as)
        menu.exec(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))

    def _on_save_as(self):
        name, ok = QInputDialog.getText(
            self, "Save As",
            "Enter a name for this result:",
            text=self._get_default_name(),
        )
        if ok and name.strip():
            self.save_as_requested.emit(name.strip())

    def _get_default_name(self) -> str:
        result = self._service.current_result
        if result and result.source_name:
            return result.source_name
        return "Untitled Result"

    def _apply_theme_styles(self):
        self._save_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: white; "
            f"border: none; border-radius: 4px; padding: 0 {Spacing.MD}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_SECONDARY}; }}"
        )
