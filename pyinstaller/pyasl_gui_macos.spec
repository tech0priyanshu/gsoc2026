# -*- mode: python ; coding: utf-8 -*-
"""
pyinstaller/pyasl_gui_macos.spec
--------------------------------
PyInstaller Specification for PyASL Pipeline GUI — macOS .app Bundle.

1. Why it exists:
   macOS-specific PyInstaller spec that produces a .app bundle. Mirrors the Analysis
   configuration from pyasl_gui.spec (Windows) but uses BUNDLE for native macOS packaging.

2. Why its location was chosen:
   Organized under pyinstaller/ alongside the existing Windows spec file.

3. Why this is preferable to modifying the existing spec:
   The Windows spec is handwritten and explicitly documented as Windows-specific. Keeping
   platform specs separate follows the project's existing pattern (installer/pyasl_setup.iss
   for Windows) and avoids fragile platform conditionals in spec files.

4. Any trade-offs:
   Shared Analysis configuration is duplicated. Changes to hidden imports or data bindings
   must be applied to both spec files.
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

# Application Icon path resolution — macOS uses .icns format
icon_file = PROJECT_ROOT / "assets" / "icon.icns"
if not icon_file.exists():
    # Fallback to .png (PyInstaller on macOS can use .png as icon)
    icon_file = PROJECT_ROOT / "assets" / "logo.png"

icon_path = str(icon_file) if icon_file.exists() else None

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
    name="PyASL-GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PyASL-GUI",
)

app = BUNDLE(
    coll,
    name="PyASL-GUI.app",
    icon=icon_path,
    bundle_identifier="org.osipi.pyasl.gui",
    info_plist={
        "CFBundleName": "PyASL-GUI",
        "CFBundleDisplayName": "PyASL Pipeline GUI",
        "CFBundleVersion": APP_VERSION,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleExecutable": "PyASL-GUI",
        "CFBundleIdentifier": "org.osipi.pyasl.gui",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    },
)
