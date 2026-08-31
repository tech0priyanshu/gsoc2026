"""
gui/controllers/settings_controller.py
----------------------------------------
Business-logic controller for the Settings tab.

Manages log-file configuration, default worker-count, and theme
persistence via ``SessionManager``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")


class SettingsController(QObject):
    """
    Signals
    -------
    log_file_changed(path)
    error(message)
    """

    log_file_changed = pyqtSignal(str)
    reset_requested = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, parent=None, session=None):
        super().__init__(parent)
        self._log_path = os.path.join(
            os.path.expanduser("~"), ".pyasl_pipeline.jsonl"
        )
        self._default_workers = 2
        self._theme = "dark"
        self._session = session          # SessionManager (optional)

    # ------------------------------------------------------------------
    # Session & Cache helpers
    # ------------------------------------------------------------------

    @property
    def cache_dir(self) -> str:
        if self._session is not None:
            return self._session.cache_dir
        return os.path.join(os.path.expanduser("~"), ".pyasl_workspace", "cache")

    def _auto_save_session(self) -> None:
        """Persist current settings to the session file."""
        if self._session is None:
            return
        self._session.set_settings({
            "log_path": self._log_path,
            "default_workers": self._default_workers,
            "theme": self._theme,
        })

    # ------------------------------------------------------------------
    # Restore from session
    # ------------------------------------------------------------------

    def restore_settings(self, settings_data: Dict[str, Any]) -> None:
        """Apply settings from previously saved session data."""
        if not settings_data:
            return

        log_path = settings_data.get("log_path", "")
        if log_path:
            self._log_path = log_path

        workers = settings_data.get("default_workers")
        if workers is not None:
            self._default_workers = max(1, min(16, int(workers)))

        theme = settings_data.get("theme", "dark")
        if theme in ("dark", "light", "system"):
            self._theme = theme

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_defaults(self) -> None:
        """Reset settings parameters to initial default values."""
        self._log_path = os.path.join(
            os.path.expanduser("~"), ".pyasl_pipeline.jsonl"
        )
        self._default_workers = 2
        self._theme = "dark"
        self._auto_save_session()

    def reset_application(self) -> None:
        """Reset settings to defaults and notify application to clear session state."""
        self.reset_defaults()
        if self._session is not None:
            self._session.reset()
        self.reset_requested.emit()

    # ------------------------------------------------------------------
    # Log file
    # ------------------------------------------------------------------

    @property
    def log_path(self) -> str:
        return self._log_path

    def set_log_file(self, path: str) -> None:
        """Apply the log-file path to the structured logger."""
        try:
            from pyasl.pipeline.structured_logger import set_log_file
            set_log_file(path)
            self._log_path = path
            self.log_file_changed.emit(path)
            self._auto_save_session()
        except Exception as exc:
            self.error.emit(str(exc))

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    @property
    def default_workers(self) -> int:
        return self._default_workers

    @default_workers.setter
    def default_workers(self, value: int) -> None:
        self._default_workers = max(1, min(16, value))
        self._auto_save_session()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    @property
    def theme(self) -> str:
        return self._theme

    @theme.setter
    def theme(self, value: str) -> None:
        if value in ("dark", "light", "system"):
            self._theme = value
            self._auto_save_session()
