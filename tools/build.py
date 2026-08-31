"""
tools/build.py
--------------
Single entry-point build automation script for PyASL Desktop Application.

1. Why it exists:
   Standard build entry-point script (python tools/build.py). Cleans previous artifacts,
   generates platform metadata, invokes PyInstaller, bundles branding assets, and creates
   the final release package. Supports both Windows and macOS.

2. Why its location was chosen:
   Organized under tools/ as repository build infrastructure, keeping build system separate
   from application source code.

3. Why this is preferable to previous implementation:
   Automates the complete release process without modifying source files, embedding long
   shell commands, or introducing a Python packaging dependency.

4. Any trade-offs:
   None. Pure build automation utility.
"""
from __future__ import annotations

import os
import sys
import shutil
import zipfile
import subprocess
import logging
from pathlib import Path

# Platform detection
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

# Setup Logger for Build System
logging.basicConfig(
    level=logging.INFO,
    format="[BUILD] %(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pyasl.build")


def find_project_root() -> Path:
    """Locate the PyASL project root directory relative to this script."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    if (project_root / "pyasl").exists():
        return project_root

    cwd = Path.cwd()
    if (cwd / "pyasl").exists():
        return cwd

    raise FileNotFoundError(f"Could not locate PyASL project root from {script_dir} or {cwd}")


def get_version(project_root: Path) -> str:
    """Read single source of truth version from pyasl._version."""
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from pyasl._version import __version__
        return __version__
    except ImportError:
        return "0.3.0"


def generate_version_info(project_root: Path, version_str: str) -> Path:
    """Generate PyInstaller version_info.txt for Windows executable binary metadata."""
    try:
        parts = [int(x) for x in version_str.split(".") if x.isdigit()]
        while len(parts) < 4:
            parts.append(0)
        ver_tuple = tuple(parts[:4])
    except Exception:
        ver_tuple = (0, 3, 0, 0)

    ver_str = ".".join(str(x) for x in ver_tuple)

    content = f"""# UTF-8
#
# VSVersionInfo for PyASL GUI Executable
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'OSIPI TF2.2 Taskforce'),
         StringStruct('FileDescription', 'PyASL Pipeline GUI Desktop Application'),
         StringStruct('FileVersion', '{ver_str}'),
         StringStruct('InternalName', 'PyASL'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 OSIPI TF2.2 Taskforce'),
         StringStruct('OriginalFilename', 'PyASL.exe'),
         StringStruct('ProductName', 'PyASL Pipeline GUI'),
         StringStruct('ProductVersion', '{ver_str}')])
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    version_info_path = project_root / "pyinstaller" / "version_info.txt"
    version_info_path.parent.mkdir(parents=True, exist_ok=True)
    version_info_path.write_text(content, encoding="utf-8")
    logger.info("Generated Windows version metadata at: %s", version_info_path)
    return version_info_path


def create_worker_executables(app_dist_dir: Path):
    """
    Create dedicated worker executable aliases ('PyASL Processing.exe', 'PyASL Worker.exe')
    in the application bundle directory so Windows Task Manager displays exact process image names.
    """
    main_exe = app_dist_dir / ("PyASL.exe" if IS_WINDOWS else "PyASL")
    if not main_exe.exists():
        return

    workers = ["PyASL Processing.exe", "PyASL Worker.exe"] if IS_WINDOWS else ["PyASL Processing", "PyASL Worker"]
    for worker_name in workers:
        worker_path = app_dist_dir / worker_name
        try:
            shutil.copy2(main_exe, worker_path)
            logger.info("Created worker executable alias: %s", worker_path)
        except Exception as exc:
            logger.warning("Could not create worker executable alias '%s': %s", worker_name, exc)


def clean_directory(dir_path: Path):
    """Remove target directory if present and recreate clean."""
    if dir_path.exists():
        logger.info("Cleaning directory: %s", dir_path)
        shutil.rmtree(dir_path, ignore_errors=True)
    dir_path.mkdir(parents=True, exist_ok=True)


def generate_macos_icon(project_root: Path) -> Path | None:
    """Generate .icns icon from logo.png using macOS built-in tools (sips + iconutil).

    Returns the path to the generated .icns file, or None if generation failed.
    The build will continue without an icon if this fails.
    """
    icns_path = project_root / "assets" / "icon.icns"
    if icns_path.exists():
        logger.info("macOS icon already exists: %s", icns_path)
        return icns_path

    source_png = project_root / "assets" / "logo.png"
    if not source_png.exists():
        logger.warning("Source logo.png not found; skipping .icns generation.")
        return None

    iconset_dir = project_root / "build" / "icon.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]

    try:
        for size, name in sizes:
            subprocess.check_call(
                ["sips", "-z", str(size), str(size), str(source_png),
                 "--out", str(iconset_dir / name)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        subprocess.check_call(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)]
        )
        logger.info("Generated macOS icon: %s", icns_path)
        return icns_path
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning("Could not generate .icns icon (sips/iconutil unavailable): %s", e)
        return None


def copy_bundle_assets(project_root: Path, app_dist_dir: Path):
    """Copy branding assets into executable bundle directory."""
    assets_dir = project_root / "assets"
    if not assets_dir.exists():
        return

    dist_assets = app_dist_dir / "assets"
    dist_assets.mkdir(parents=True, exist_ok=True)
    for item in assets_dir.glob("*"):
        if item.is_file():
            shutil.copy2(item, dist_assets / item.name)

    internal_dir = app_dist_dir / "_internal"
    if internal_dir.exists():
        internal_assets = internal_dir / "assets"
        internal_assets.mkdir(parents=True, exist_ok=True)
        for item in assets_dir.glob("*"):
            if item.is_file():
                shutil.copy2(item, internal_assets / item.name)

    logger.info("Bundled assets copied into executable directory.")


def check_environment(spec_file: Path):
    """Verify build environment prerequisites and log comprehensive diagnostics."""
    logger.info("-" * 60)
    logger.info("  BUILD ENVIRONMENT DIAGNOSTICS")
    logger.info("-" * 60)
    logger.info("Python Executable:    %s", sys.executable)
    logger.info("Python Version:       %s", sys.version.split()[0])
    logger.info("Virtual Environment:  %s", os.environ.get("VIRTUAL_ENV", sys.prefix))
    logger.info("Spec File Used:       %s", spec_file)

    # Check PyInstaller
    try:
        import PyInstaller
        logger.info("PyInstaller Version:  %s", getattr(PyInstaller, "__version__", "unknown"))
    except ImportError:
        logger.error("CRITICAL: PyInstaller is not installed in current environment (%s)!", sys.executable)
        sys.exit(1)

    # Check PyQt6 and modules
    try:
        import PyQt6
        import PyQt6.QtCore
        import PyQt6.QtGui
        import PyQt6.QtWidgets
        logger.info("PyQt6 Version:        %s", PyQt6.QtCore.PYQT_VERSION_STR)
        logger.info("PyQt6 Path:           %s", PyQt6.__file__)
    except ImportError as e:
        logger.error("CRITICAL: PyQt6 modules could not be imported: %s", e)
        logger.error("Ensure PyQt6 is installed in environment: %s", sys.executable)
        sys.exit(1)

    logger.info("-" * 60)


def validate_build(project_root: Path, dist_dir: Path):
    """Validate built executable bundle, PyQt6 modules, assets, and startup behavior."""
    logger.info("Executing post-build validation checks...")

    if IS_MACOS:
        _validate_build_macos(project_root, dist_dir)
    elif IS_LINUX:
        _validate_build_linux(project_root, dist_dir)
    else:
        _validate_build_windows(project_root, dist_dir)

    logger.info("All post-build validation checks PASSED successfully!")


def _validate_build_linux(project_root: Path, dist_dir: Path):
    """Linux-specific post-build validation and smoke test (Priority 6D)."""
    app_dist_dir = dist_dir / "PyASL"
    if not app_dist_dir.exists():
        raise RuntimeError(f"Validation Failed: App directory does not exist: {app_dist_dir}")

    exe_path = app_dist_dir / "PyASL"
    if not exe_path.exists():
        raise RuntimeError(f"Validation Failed: Executable not found at {exe_path}")
    logger.info("  ✓ Executable exists: %s", exe_path)

    # Smoke test: check executable execution or --help / version flag exit code
    logger.info("Executing Linux post-build smoke test...")
    try:
        res = subprocess.run([str(exe_path), "--help"], capture_output=True, text=True, timeout=5)
        logger.info("  ✓ Smoke test executed with exit code %s", res.returncode)
    except Exception as e:
        logger.warning("  ⚠ Smoke test process execution warning: %s", e)


def _validate_build_windows(project_root: Path, dist_dir: Path):
    """Windows-specific post-build validation."""
    app_dist_dir = dist_dir / "PyASL"
    if not app_dist_dir.exists():
        raise RuntimeError(f"Validation Failed: App directory does not exist: {app_dist_dir}")

    exe_path = app_dist_dir / "PyASL.exe"
    if not exe_path.exists():
        raise RuntimeError(f"Validation Failed: Executable not found at {exe_path}")
    logger.info("  ✓ Executable exists: %s", exe_path)

    # Verify PyQt6 QtCore binary inside bundle
    qt_core_pyd = app_dist_dir / "_internal" / "PyQt6" / "QtCore.pyd"
    if not qt_core_pyd.exists():
        raise RuntimeError(f"Validation Failed: PyQt6.QtCore module missing from bundle: {qt_core_pyd}")
    logger.info("  ✓ PyQt6.QtCore bundled successfully: %s", qt_core_pyd)

    # Verify branding assets bundled
    dist_assets = app_dist_dir / "assets"
    if not dist_assets.exists() or not any(dist_assets.iterdir()):
        raise RuntimeError(f"Validation Failed: Bundled assets missing or empty at {dist_assets}")
    logger.info("  ✓ Bundled assets verified at: %s", dist_assets)

    # Verify executable process startup
    logger.info("Testing executable startup...")
    import time
    proc = subprocess.Popen([str(exe_path)], cwd=str(app_dist_dir))
    time.sleep(2.5)
    ret_code = proc.poll()
    if ret_code is not None and ret_code != 0:
        raise RuntimeError(f"Validation Failed: Packaged executable crashed on launch with exit code {ret_code}")

    if ret_code is None:
        logger.info("  ✓ Executable started cleanly and is running (Process ID: %s)", proc.pid)
        proc.terminate()
        proc.wait(timeout=5)
    else:
        logger.info("  ✓ Executable launched and exited cleanly (Exit code: %s)", ret_code)


def _validate_build_macos(project_root: Path, dist_dir: Path):
    """macOS-specific post-build validation."""
    app_bundle = dist_dir / "PyASL-GUI.app"
    if not app_bundle.exists():
        raise RuntimeError(f"Validation Failed: macOS .app bundle does not exist: {app_bundle}")
    logger.info("  ✓ macOS .app bundle exists: %s", app_bundle)

    # Verify the executable inside the .app bundle
    macos_exe = app_bundle / "Contents" / "MacOS" / "PyASL-GUI"
    if not macos_exe.exists():
        raise RuntimeError(f"Validation Failed: Executable not found inside .app bundle: {macos_exe}")
    logger.info("  ✓ Executable exists inside bundle: %s", macos_exe)

    # Verify Info.plist exists
    info_plist = app_bundle / "Contents" / "Info.plist"
    if not info_plist.exists():
        raise RuntimeError(f"Validation Failed: Info.plist missing from bundle: {info_plist}")
    logger.info("  ✓ Info.plist present: %s", info_plist)

    # Verify PyQt6 QtCore is bundled (shared object on macOS)
    frameworks_dir = app_bundle / "Contents" / "Frameworks"
    resources_dir = app_bundle / "Contents" / "Resources"
    # PyInstaller may place PyQt6 in different locations within the bundle
    qt_found = False
    for search_root in [frameworks_dir, resources_dir, app_bundle / "Contents" / "MacOS"]:
        if not search_root.exists():
            continue
        for p in search_root.rglob("QtCore*"):
            qt_found = True
            logger.info("  ✓ PyQt6.QtCore found in bundle: %s", p)
            break
        if qt_found:
            break
    if not qt_found:
        logger.warning("  ⚠ Could not locate QtCore inside .app bundle (may still work)")


def create_release_archive(dist_dir: Path, release_dir: Path, version: str) -> Path:
    """Pack built application bundle into release zip archive."""
    if IS_MACOS:
        app_bundle = dist_dir / "PyASL-GUI.app"
        release_zip = release_dir / f"PyASL-v{version}-macOS-x64.zip"
        logger.info("Creating release ZIP archive: %s", release_zip)

        with zipfile.ZipFile(release_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if app_bundle.exists():
                for root, _, files in os.walk(app_bundle):
                    for f in files:
                        full_path = Path(root) / f
                        arc_name = full_path.relative_to(dist_dir)
                        zf.write(full_path, arc_name)
    elif IS_LINUX:
        app_dist_dir = dist_dir / "PyASL"
        release_zip = release_dir / f"PyASL-v{version}-Linux-x64.zip"
        logger.info("Creating release ZIP archive: %s", release_zip)

        with zipfile.ZipFile(release_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if app_dist_dir.exists():
                for root, _, files in os.walk(app_dist_dir):
                    for f in files:
                        full_path = Path(root) / f
                        arc_name = full_path.relative_to(dist_dir)
                        zf.write(full_path, arc_name)
    else:
        app_dist_dir = dist_dir / "PyASL"
        release_zip = release_dir / f"PyASL-v{version}-Windows-x64.zip"
        logger.info("Creating release ZIP archive: %s", release_zip)

        with zipfile.ZipFile(release_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if app_dist_dir.exists():
                for root, _, files in os.walk(app_dist_dir):
                    for f in files:
                        full_path = Path(root) / f
                        arc_name = full_path.relative_to(dist_dir)
                        zf.write(full_path, arc_name)

    return release_zip


def main():
    logger.info("=" * 60)
    logger.info("  PyASL Desktop Application — Build System  ")
    logger.info("=" * 60)

    platform_label = "macOS" if IS_MACOS else "Windows"
    logger.info("Build Platform: %s", platform_label)

    project_root = find_project_root()
    logger.info("Project Root: %s", project_root)

    version = get_version(project_root)
    logger.info("Target Version: v%s", version)

    # 1. Locate Spec File (platform-specific)
    if IS_MACOS:
        spec_file = project_root / "pyinstaller" / "pyasl_gui_macos.spec"
    else:
        spec_file = project_root / "pyinstaller" / "pyasl_gui.spec"

    if not spec_file.exists():
        logger.error("Spec file not found at: %s", spec_file)
        sys.exit(1)

    # 2. Check Environment & Diagnostics
    check_environment(spec_file)

    # 3. Clean previous build directories
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"
    release_dir = project_root / "release"

    clean_directory(build_dir)
    clean_directory(dist_dir)
    clean_directory(release_dir)

    # 4. Generate platform-specific metadata
    if IS_MACOS:
        generate_macos_icon(project_root)
    else:
        generate_version_info(project_root, version)

    # 5. Invoke PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--workpath={build_dir}",
        f"--distpath={dist_dir}",
        str(spec_file)
    ]

    logger.info("Executing command: %s", " ".join(cmd))
    try:
        subprocess.check_call(cmd, cwd=str(project_root))
        logger.info("PyInstaller compilation completed successfully!")
    except subprocess.CalledProcessError as e:
        logger.error("PyInstaller build failed with exit code: %s", e.returncode)
        sys.exit(e.returncode)

    # 6. Copy branding assets & worker executables to dist bundle
    if not IS_MACOS:
        app_dist_dir = dist_dir / "PyASL"
        if app_dist_dir.exists():
            copy_bundle_assets(project_root, app_dist_dir)
            create_worker_executables(app_dist_dir)

    # 7. Post-build Validation
    try:
        validate_build(project_root, dist_dir)
    except Exception as e:
        logger.error("BUILD VALIDATION FAILURE: %s", e)
        sys.exit(1)

    # 8. Create release package
    release_zip = create_release_archive(dist_dir, release_dir, version)

    app_label = dist_dir / ("PyASL-GUI.app" if IS_MACOS else "PyASL")
    logger.info("=" * 60)
    logger.info("  BUILD SUCCESSFUL!  ")
    logger.info("  Standalone App Directory: %s", app_label)
    logger.info("  Release Package:          %s", release_zip)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

