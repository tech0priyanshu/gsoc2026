# -*- mode: python ; coding: utf-8 -*-
"""
pyinstaller/pyasl_gui.spec
--------------------------
Handwritten PyInstaller Specification for PyASL Pipeline GUI Desktop Application.

1. Why it exists:
   Version-controlled, handwritten PyInstaller spec for building standalone executables
   with PyQt6 UI, multiprocessing freeze safety, QSS stylesheets, and branding assets.

2. Why its location was chosen:
   Organized under pyinstaller/ as part of repository packaging infrastructure.

3. Why this is preferable to previous implementation:
   Replaces auto-generated root specs. Keeps spec file isolated from source code while
   maintaining explicit control over hidden imports, excluded modules, assets, and Windows binary metadata.

4. Any trade-offs:
   Manual updates are required if new hidden dynamic C-extensions are added to dependencies.
"""
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

# Spec directory and Project Root (PyASL directory)
try:
    SPEC_DIR = Path(SPECPATH).resolve()
except NameError:
    SPEC_DIR = Path(__file__).parent.resolve()

PROJECT_ROOT = SPEC_DIR.parent.resolve()

ENTRY_POINT = str(PROJECT_ROOT / "launch_gui.py")

# Ensure project root is in sys.path during spec evaluation
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Read single source of truth version
try:
    from pyasl._version import __version__ as APP_VERSION
except ImportError:
    APP_VERSION = "0.3.0"

# Asset and resource data bindings
datas = []

# Centralized branding assets
assets_dir = PROJECT_ROOT / "assets"
if assets_dir.exists():
    datas.append((str(assets_dir), "assets"))

# GUI styles and package resources
gui_styles = PROJECT_ROOT / "pyasl" / "gui" / "styles"
if gui_styles.exists():
    datas.append((str(gui_styles), "pyasl/gui/styles"))

gui_resources = PROJECT_ROOT / "pyasl" / "gui" / "resources"
if gui_resources.exists():
    datas.append((str(gui_resources), "pyasl/gui/resources"))

# PyQt6 extra data files (e.g. plugins, translations)
datas += collect_data_files("PyQt6", include_py_files=False)

# Dynamic binaries for PyQt6
binaries = collect_dynamic_libs("PyQt6")

# Collect submodules for PyQt6 and PyASL package graph dynamically using PyInstaller hook utilities
hiddenimports = list(set(
    collect_submodules("PyQt6") +
    collect_submodules("pyasl") +
    ["multiprocessing"]
))

# Application Icon path resolution
icon_file = PROJECT_ROOT / "assets" / "icon.ico"
if not icon_file.exists():
    icon_file = PROJECT_ROOT / "assets" / "logo.ico"
if not icon_file.exists():
    icon_file = PROJECT_ROOT / "pyasl" / "gui" / "resources" / "logo.ico"

icon_path = str(icon_file) if icon_file.exists() else None

# Windows Version Info resource file (generated during build)
version_info_file = SPEC_DIR / "version_info.txt"
version_info_path = str(version_info_file) if version_info_file.exists() else None

a = Analysis(
    [ENTRY_POINT],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib.tests",
        "scipy.spatial.tests",
        "IPython",
        "notebook",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PyASL",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    version=version_info_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PyASL",
)
