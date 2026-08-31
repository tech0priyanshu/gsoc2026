"""
gui/utils/process_helper.py
----------------------------
Utilities for cross-platform process naming, process identity initialization,
and executable resolution for PyASL desktop application processes.
"""
from __future__ import annotations

import ctypes
import logging
import multiprocessing
import os
import sys
from typing import Optional

logger = logging.getLogger("pyasl.process_helper")


def is_frozen() -> bool:
    """Check if the application is running inside a PyInstaller frozen bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_app_dir() -> str:
    """Get directory containing the executable or main script."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def set_process_identity(role_name: str) -> None:
    """
    Set process identity, multiprocessing name, and Windows process/console title.

    Parameters
    ----------
    role_name : str
        Name of the process role (e.g., 'PyASL', 'PyASL Processing', 'PyASL Worker')
    """
    try:
        current = multiprocessing.current_process()
        current.name = role_name
    except Exception as exc:
        logger.debug("Failed to set multiprocessing process name: %s", exc)

    if sys.platform == "win32":
        # 1. Set Windows Console Title if console attached or available
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(f"{role_name} (PID {os.getpid()})")
        except Exception:
            pass

        # 2. Set AppUserModelID for Windows process grouping
        try:
            app_id = f"OSIPI.PyASL.{role_name.replace(' ', '')}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass


def get_worker_executable(role_name: str) -> str:
    """
    Locate dedicated worker executable if running in packaged mode.

    Returns the path to 'PyASL Processing.exe' or 'PyASL Worker.exe' if present,
    otherwise returns sys.executable.
    """
    if not is_frozen():
        return sys.executable

    app_dir = get_app_dir()
    exe_name = f"{role_name}.exe"
    target_path = os.path.join(app_dir, exe_name)

    if os.path.isfile(target_path):
        return target_path

    return sys.executable
