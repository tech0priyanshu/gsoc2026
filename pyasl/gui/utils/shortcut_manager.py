"""
gui/utils/shortcut_manager.py
-------------------------------
Centralized, context-aware shortcut manager for PyASL GUI.

Ensures keyboard shortcuts (Ctrl+S, Space, F5, Esc, etc.) do not fire
when focus is inside text entry widgets (QLineEdit, QTextEdit, QPlainTextEdit).
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

try:
    from PyQt6.QtCore import QObject, Qt  # type: ignore
    from PyQt6.QtGui import QKeySequence, QShortcut  # type: ignore
    from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit, QWidget  # type: ignore
except ImportError:
    raise ImportError("PyQt6 is required for ShortcutManager.")


class ShortcutManager(QObject):
    """
    Registers and manages application-wide keyboard shortcuts with focus checking.
    """

    def __init__(self, parent_window: QWidget) -> None:
        super().__init__(parent_window)
        self._window = parent_window
        self._shortcuts: Dict[str, QShortcut] = {}

    @staticmethod
    def is_text_editing() -> bool:
        """Return True if currently focused widget is a text input control."""
        focus_w = QApplication.focusWidget()
        if focus_w is None:
            return False
        return isinstance(focus_w, (QLineEdit, QTextEdit, QPlainTextEdit))

    def register_shortcut(
        self,
        key_sequence: str,
        callback: Callable[[], None],
        context_aware: bool = True,
    ) -> QShortcut:
        """
        Register a shortcut key sequence (e.g., 'Ctrl+S', 'F5').

        If *context_aware* is True, the callback is suppressed when
        the user is actively editing text.
        """
        shortcut = QShortcut(QKeySequence(key_sequence), self._window)

        def _handler():
            if context_aware and self.is_text_editing():
                return
            callback()

        shortcut.activated.connect(_handler)
        self._shortcuts[key_sequence] = shortcut
        return shortcut

    def unregister_all(self) -> None:
        """Disconnect and clear all registered shortcuts."""
        for sc in self._shortcuts.values():
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts.clear()
