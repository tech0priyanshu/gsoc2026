"""
gui/views/result_window/search_bar.py
----------------------------------------
Debounced global search widget for the result window.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtWidgets import (
        QWidget, QHBoxLayout, QLineEdit, QPushButton,
    )
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens

logger = logging.getLogger(__name__)


class SearchBar(QWidget):
    """
    Debounced search bar for result data.

    Emits ``search_changed(query)`` after 300ms of inactivity.
    """

    search_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._emit_search)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XS)

        self._input = QLineEdit()
        self._input.setAccessibleName("Search results")
        self._input.setObjectName("result_search_input")
        self._input.setPlaceholderText("🔍 Search results…")
        self._input.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {Colors.BG_SECONDARY}; "
            f"color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 4px; padding: 0 {Spacing.SM}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QLineEdit:focus {{ border-color: {Colors.ACCENT_PRIMARY}; }}"
        )
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        # Clear button
        self._clear_btn = QPushButton("✕")
        self._clear_btn.setAccessibleName("Clear search")
        self._clear_btn.setFixedSize(DesignTokens.TOOLBAR_BTN_HEIGHT, DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: none; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        self._clear_btn.clicked.connect(self._clear)
        self._clear_btn.hide()
        layout.addWidget(self._clear_btn)

    def _on_text_changed(self, text: str):
        self._timer.start()
        self._clear_btn.setVisible(bool(text))

    def _emit_search(self):
        self.search_changed.emit(self._input.text())

    def _clear(self):
        self._input.clear()
        self.search_changed.emit("")

    def text(self) -> str:
        return self._input.text()

    def _apply_theme_styles(self):
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {Colors.BG_SECONDARY}; "
            f"color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 4px; padding: 0 {Spacing.SM}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QLineEdit:focus {{ border-color: {Colors.ACCENT_PRIMARY}; }}"
        )
