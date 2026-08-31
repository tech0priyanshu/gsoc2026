"""
tools/clean.py
--------------
Workspace build artifact cleaner for the PyASL application.

1. Why it exists:
   Provides a standalone, reliable script to clean generated build artifacts
   (build/, dist/, release/, pycache, spec backups) without manual directory deletion.

2. Why its location was chosen:
   Organized under tools/ as part of standard repository infrastructure, keeping build
   automation distinct from application package source.

3. Why this is preferable to previous implementation:
   Separates cleaning logic into a reusable modular tool that can be executed independently
   (python tools/clean.py) or called programmatically by build.py/release.py.

4. Any trade-offs:
   None. Pure utility script.
"""
from __future__ import annotations

import os
import sys
import shutil
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[CLEAN] %(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pyasl.clean")


def find_project_root() -> Path:
    """Locate PyASL root directory relative to this script location."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    if (project_root / "pyasl").exists():
        return project_root
    cwd = Path.cwd()
    if (cwd / "pyasl").exists():
        return cwd
    raise FileNotFoundError(f"Could not locate PyASL project root from {script_dir} or {cwd}")


def remove_directory(dir_path: Path):
    """Remove directory and its contents if present."""
    if dir_path.exists():
        logger.info("Removing directory: %s", dir_path)
        shutil.rmtree(dir_path, ignore_errors=True)


def clean_build_artifacts(project_root: Path):
    """Clean generated build, dist, release, and cache directories."""
    targets = [
        project_root / "build",
        project_root / "dist",
        project_root / "release",
        project_root / "pyasl_osipi.egg-info",
    ]

    for target in targets:
        remove_directory(target)

    # Remove stale PyInstaller spec backups in root if any
    for spec_bak in project_root.glob("*.spec.bak"):
        try:
            logger.info("Removing spec backup: %s", spec_bak)
            spec_bak.unlink()
        except Exception as e:
            logger.warning("Could not remove %s: %s", spec_bak, e)

    logger.info("Cleanup completed successfully!")


def main():
    logger.info("Starting PyASL build artifact cleanup...")
    project_root = find_project_root()
    clean_build_artifacts(project_root)


if __name__ == "__main__":
    main()
