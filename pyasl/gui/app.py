"""
gui/app.py
----------
Application bootstrap: load theme, create QApplication, show MainWindow.
"""
from __future__ import annotations

import os
import sys


def _load_stylesheet() -> str:
    qss_path = os.path.join(os.path.dirname(__file__), "styles", "dark_theme.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def create_app(argv=None):
    """Create and configure the QApplication."""
    from pyasl.gui.utils.resource_helper import setup_app_user_model_id, get_logo_icon

    # Set Windows AppUserModelID BEFORE creating QApplication instance so taskbar icon displays properly
    setup_app_user_model_id("osipi.pyasl.gui.v1")

    try:
        from PyQt6.QtWidgets import QApplication  # type: ignore
        from PyQt6.QtGui import QFont, QIcon       # type: ignore
        from PyQt6.QtCore import Qt                # type: ignore
    except ImportError:
        print(
            "ERROR: PyQt6 is not installed.\n"
            "Install it with:  pip install PyQt6\n"
        )
        sys.exit(1)

    app = QApplication(argv or sys.argv)
    app.setApplicationName("PyASL")
    app.setApplicationDisplayName("PyASL Pipeline GUI")
    app.setOrganizationName("OSIPI TF2.2")

    # Set application icon
    icon = get_logo_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    # High-DPI support
    app.setStyleSheet(_load_stylesheet())

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    return app


def run():
    """Create the application and run the main event loop."""
    app = create_app()
    from .views.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
