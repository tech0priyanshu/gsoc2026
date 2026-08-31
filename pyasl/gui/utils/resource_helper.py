"""
gui/utils/resource_helper.py
----------------------------
Centralized loader for first-party application branding assets.
Ensures application logos (logo.png, logo.ico) are resolved reliably across environments
without falling back to placeholders or silent omissions.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path

try:
    from PyQt6.QtGui import QIcon, QPixmap  # type: ignore
    from PyQt6.QtCore import Qt  # type: ignore
except ImportError:
    pass

logger = logging.getLogger(__name__)


def get_asset_dir() -> Path:
    """Return the primary assets directory depending on runtime environment."""
    import sys
    # 1. PyInstaller frozen executable environment
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass_assets = Path(sys._MEIPASS) / "assets"
        if meipass_assets.exists():
            return meipass_assets
        return Path(sys._MEIPASS)

    # 2. Development / installed package environment
    gui_dir = Path(__file__).resolve().parent.parent  # pyasl/gui
    
    # Check PyASL/assets (project root level assets)
    project_root_assets = gui_dir.parent.parent / "assets"
    if project_root_assets.exists():
        return project_root_assets

    # Check repository root assets
    repo_root_assets = gui_dir.parent.parent.parent / "assets"
    if repo_root_assets.exists():
        return repo_root_assets

    # Default to pyasl/gui/resources
    return gui_dir / "resources"


def get_logo_path(filename: str = "logo.png") -> str:
    """
    Return the absolute path to the official PyASL application logo/asset.

    Resolves reliably across:
    - PyInstaller standalone executables (_MEIPASS)
    - Centralized repository assets (assets/)
    - Package GUI resources (pyasl/gui/resources/)
    - Documentation fallbacks (docs/assets/osipiImgs/)
    """
    asset_dir = get_asset_dir()

    # 1. Direct match in resolved asset directory
    target_path = asset_dir / filename
    if target_path.exists():
        return str(target_path.resolve())

    # 2. Alternate filename mapping (icon.ico -> logo.ico, etc.)
    alt_name = "logo.ico" if filename in ("icon.ico", "logo.png") else "logo.png"
    alt_path = asset_dir / alt_name
    if alt_path.exists():
        return str(alt_path.resolve())

    # 3. Secondary check in pyasl/gui/resources
    gui_dir = Path(__file__).resolve().parent.parent
    gui_resources = gui_dir / "resources" / filename
    if gui_resources.exists():
        return str(gui_resources.resolve())

    # 4. Fallback path: docs/assets/osipiImgs/ in repo root
    try:
        repo_root = gui_dir.parents[2]
        docs_img_dir = repo_root / "docs" / "assets" / "osipiImgs"
        doc_logo = (
            docs_img_dir / "osipi_logo.ico"
            if filename.endswith(".ico")
            else docs_img_dir / "OSIPI_logo.png"
        )
        if doc_logo.exists():
            return str(doc_logo.resolve())
    except Exception as e:
        logger.debug("Failed repo-root logo lookup: %s", e)

    logger.warning("Application asset '%s' not found at primary path: %s", filename, target_path)
    return str(target_path.resolve())


def get_logo_pixmap(width: int = 40, height: int = 40) -> QPixmap:
    """
    Load the official application logo as a smoothly scaled QPixmap.
    """
    path = get_logo_path("logo.png")
    if os.path.exists(path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return pixmap.scaled(
                width, height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
    logger.warning("Could not load valid QPixmap from logo path: %s", path)
    return QPixmap()


def setup_app_user_model_id(app_id: str = "osipi.pyasl.gui.v1") -> None:
    """
    Set process AppUserModelID on Windows so the taskbar displays the custom icon
    instead of falling back to python.exe default icon. Must be called before creating windows.
    """
    import sys
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass


def get_logo_icon() -> QIcon:
    """
    Load the official application logo as a QIcon for window/taskbar decoration.
    """
    icon = QIcon()
    ico_path = get_logo_path("logo.ico")
    if os.path.exists(ico_path):
        icon.addFile(ico_path)

    png_path = get_logo_path("logo.png")
    if os.path.exists(png_path):
        icon.addFile(png_path)

    return icon


