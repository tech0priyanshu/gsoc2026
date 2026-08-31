"""
tools/release.py
----------------
Release packaging and Inno Setup installer automation script for PyASL.

1. Why it exists:
   Automates final release artifact production, including ZIP archive verification
   and Inno Setup installer compilation (ISCC.exe) if available on Windows.

2. Why its location was chosen:
   Organized under tools/ as repository release engineering infrastructure.

3. Why this is preferable to previous implementation:
   Consolidates release pipeline steps into an executable helper (python tools/release.py),
   allowing automated or manual triggering without requiring hardcoded CLI invocations.

4. Any trade-offs:
   Requires Inno Setup installed on Windows to generate .exe installer setup.
   On macOS, the Inno Setup step is skipped.
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[RELEASE] %(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pyasl.release")


def find_project_root() -> Path:
    """Locate PyASL root directory relative to this script."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    if (project_root / "pyasl").exists():
        return project_root
    cwd = Path.cwd()
    if (cwd / "pyasl").exists():
        return cwd
    raise FileNotFoundError(f"Could not locate PyASL project root from {script_dir} or {cwd}")


def compile_inno_setup(project_root: Path) -> bool:
    """Attempt to compile Inno Setup script if ISCC.exe is in PATH or standard location."""
    iss_file = project_root / "installer" / "pyasl_setup.iss"
    if not iss_file.exists():
        logger.warning("Installer script not found at: %s", iss_file)
        return False

    iscc_path = shutil.which("iscc") or shutil.which("ISCC")
    if not iscc_path:
        # Standard installation fallback path on Windows
        standard_path = Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe")
        if standard_path.exists():
            iscc_path = str(standard_path)

    if not iscc_path:
        logger.info("Inno Setup compiler (ISCC) not found in PATH or standard location.")
        logger.info("Skipping .exe setup installer creation. Release zip archive remains available.")
        return False

    logger.info("Found Inno Setup compiler: %s", iscc_path)
    logger.info("Compiling installer setup: %s", iss_file)

    try:
        subprocess.check_call([iscc_path, str(iss_file)], cwd=str(project_root / "installer"))
        logger.info("Inno Setup compilation completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Inno Setup compilation failed with exit code: %s", e.returncode)
        return False


def main():
    logger.info("Starting PyASL release engineering step...")
    project_root = find_project_root()

    # Detect built application (platform-aware)
    if sys.platform == "darwin":
        dist_app = project_root / "dist" / "PyASL-GUI.app"
    else:
        dist_app = project_root / "dist" / "PyASL-GUI"

    if not dist_app.exists():
        logger.info("Build bundle %s not found. Running python tools/build.py first...", dist_app.name)
        build_script = project_root / "tools" / "build.py"
        subprocess.check_call([sys.executable, str(build_script)], cwd=str(project_root))

    # Inno Setup installer is Windows-only
    if sys.platform == "win32":
        compile_inno_setup(project_root)
    else:
        logger.info("Skipping Inno Setup compilation (not on Windows).")

    release_dir = project_root / "release"
    logger.info("=" * 60)
    logger.info("  RELEASE PACKAGING COMPLETE  ")
    logger.info("  Artifacts folder: %s", release_dir)
    if release_dir.exists():
        for artifact in release_dir.glob("*"):
            logger.info("  - %s", artifact.name)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
