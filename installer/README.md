# PyASL Windows Installer Infrastructure

This directory contains Inno Setup installer scripts and documentation for creating Windows installer executables (`.exe`).

## Build Instructions

1. Ensure [Inno Setup](https://jrsoftware.org/isinfo.php) is installed on your system.
2. Build the PyInstaller standalone application:
   ```bash
   python tools/build.py
   ```
3. Compile the Inno Setup installer:
   - Command line: `iscc installer/pyasl_setup.iss`
   - Or run release script: `python tools/release.py`

The resulting installer setup package will be placed in `release/PyASL-GUI-v<version>-Setup.exe`.
