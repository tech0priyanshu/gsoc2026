"""
gui/utils/log_helper.py
-----------------------
Structured logging configuration helper for the PyASL application.
Configures consistent stream and file logging with user-specific log directory support.
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

_LOGGING_INITIALIZED = False


def get_app_base_dir() -> Path:
    """Return standard user application base directory according to OS conventions."""
    if sys.platform == "win32":
        base_dir = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        app_dir = Path(base_dir) / "PyASL"
    elif sys.platform == "darwin":
        app_dir = Path.home() / "Library" / "Application Support" / "PyASL"
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        app_dir = Path(config_home) / "pyasl"
    return app_dir


def ensure_app_directories() -> dict[str, Path]:
    """
    Ensure standard application directories exist according to OS conventions:
    - Windows: %LOCALAPPDATA%/PyASL/ (logs/, config/, cache/, temp/)
    - macOS: ~/Library/Application Support/PyASL/
    - Linux: ~/.config/pyasl/

    Returns dictionary mapping directory names to resolved Path objects.
    """
    base_dir = get_app_base_dir()
    subdirs = ["logs", "config", "cache", "temp"]
    dirs: dict[str, Path] = {}
    for sub in subdirs:
        d = base_dir / sub
        try:
            d.mkdir(parents=True, exist_ok=True)
            dirs[sub] = d
        except Exception:
            fallback = Path.cwd() / sub
            fallback.mkdir(exist_ok=True)
            dirs[sub] = fallback
    return dirs


def get_user_log_dir() -> Path:
    """
    Return user-specific log directory according to OS standard locations.
    Also ensures config, cache, and temp directories are initialized.
    """
    app_dirs = ensure_app_directories()
    return app_dirs["logs"]


def setup_app_logging(level: int = logging.INFO, log_filename: str = "pyasl_gui.log") -> logging.Logger:
    """
    Configure application-wide structured logging.
    
    Creates a StreamHandler (stdout) and a FileHandler in the user log directory.
    Safe to call multiple times (idempotent).
    """
    global _LOGGING_INITIALIZED
    root_logger = logging.getLogger()
    
    if _LOGGING_INITIALIZED:
        return root_logger

    root_logger.setLevel(level)

    # Formatter for structured logs
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Stream Handler (console output)
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)
    if not has_stream:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File Handler in user log directory
    try:
        log_dir = get_user_log_dir()
        log_file = log_dir / log_filename
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        root_logger.warning("Could not set up file log handler: %s", e)

    _LOGGING_INITIALIZED = True
    return root_logger
