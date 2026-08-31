# PyASL Desktop Application — Release Guide

## Overview

PyASL produces standalone desktop application releases for **Windows** and **macOS**. Both platforms use [PyInstaller](https://pyinstaller.org/) to bundle the PyQt6 GUI into a self-contained package.

| Platform | Build Artifact | Distribution Format |
|----------|---------------|---------------------|
| Windows  | `PyASL-GUI.exe` + support files | ZIP archive + optional Inno Setup installer |
| macOS    | `PyASL-GUI.app` bundle | ZIP archive |

## Local Build

### Prerequisites

- Python 3.10+
- Virtual environment with dependencies installed:
  ```bash
  pip install pyinstaller PyQt6 PyQt6-Qt6 PyQt6-sip
  pip install -e ".[gui,pipeline]"
  ```

### Build Command (Both Platforms)

```bash
cd PyASL
python tools/build.py
```

The build script automatically detects the platform and:
- **Windows**: Uses `pyinstaller/pyasl_gui.spec`, produces `release/PyASL-v{version}-Windows-x64.zip`
- **macOS**: Uses `pyinstaller/pyasl_gui_macos.spec`, produces `release/PyASL-v{version}-macOS-x64.zip`

### Release Command (Windows Only — Inno Setup)

```bash
python tools/release.py
```

This additionally compiles the Inno Setup installer (`installer/pyasl_setup.iss`) if ISCC is available on the system. This step is skipped on macOS.

## CI/CD Release Workflow

The GitHub Actions workflow (`.github/workflows/release.yml`) automates release builds.

### Trigger

- **Automatic**: Push a version tag (e.g., `git tag v0.3.0 && git push --tags`)
- **Manual**: Use the "Run workflow" button in GitHub Actions

### What It Does

1. Builds the Windows release on `windows-latest`
2. Builds the macOS release on `macos-latest`
3. Creates a GitHub Release with both ZIP artifacts attached

### Artifacts Produced

- `PyASL-v{version}-Windows-x64.zip`
- `PyASL-v{version}-macOS-x64.zip`

## macOS-Specific Notes

### Application Icon

macOS uses `.icns` format for application icons. The build script attempts to generate `assets/icon.icns` from the existing `assets/logo.png` using macOS built-in tools (`sips` + `iconutil`). If these tools are unavailable, the build falls back to using `logo.png` directly (PyInstaller supports `.png` as a macOS icon fallback).

To pre-generate the `.icns` file manually on macOS:

```bash
mkdir -p icon.iconset
sips -z 1024 1024 assets/logo.png --out icon.iconset/icon_512x512@2x.png
sips -z 512 512 assets/logo.png --out icon.iconset/icon_512x512.png
sips -z 256 256 assets/logo.png --out icon.iconset/icon_256x256.png
sips -z 128 128 assets/logo.png --out icon.iconset/icon_128x128.png
sips -z 64 64 assets/logo.png --out icon.iconset/icon_32x32@2x.png
sips -z 32 32 assets/logo.png --out icon.iconset/icon_32x32.png
sips -z 16 16 assets/logo.png --out icon.iconset/icon_16x16.png
iconutil -c icns icon.iconset -o assets/icon.icns
rm -rf icon.iconset
```

### Unsigned Application Warning

The macOS `.app` bundle is **not signed or notarized** by default. On first launch, macOS Gatekeeper will block the application. Users must:

1. Right-click (or Control-click) on `PyASL-GUI.app`
2. Select **Open** from the context menu
3. Click **Open** in the confirmation dialog

This only needs to be done once.

### Signing & Notarization (Future)

To enable code signing and notarization, the following are required:

1. **Apple Developer ID Application certificate** (requires paid Apple Developer Program membership)
2. **Entitlements file** (`entitlements.plist`) — add to `pyinstaller/` directory
3. **GitHub Secrets** for CI:
   - `MACOS_CERTIFICATE` — Base64-encoded `.p12` certificate
   - `MACOS_CERTIFICATE_PASSWORD` — Certificate password
   - `APPLE_ID` — Apple Developer account email
   - `APPLE_APP_SPECIFIC_PASSWORD` — App-specific password for notarization
   - `APPLE_TEAM_ID` — Apple Developer Team ID

4. Update `pyinstaller/pyasl_gui_macos.spec`:
   ```python
   codesign_identity="Developer ID Application: Your Name (TEAM_ID)",
   entitlements_file=str(SPEC_DIR / "entitlements.plist"),
   ```

5. Add notarization step to `.github/workflows/release.yml` after the build step.

## Version Management

Version is defined in `pyasl/_version.py` (single source of truth). The build script reads this automatically. Update version there before creating a release tag.

## Platform-Specific Files

| File | Platform | Purpose |
|------|----------|---------|
| `pyinstaller/pyasl_gui.spec` | Windows | PyInstaller spec with Windows version metadata |
| `pyinstaller/pyasl_gui_macos.spec` | macOS | PyInstaller spec with .app BUNDLE |
| `pyinstaller/version_info.txt` | Windows | Generated Windows executable metadata |
| `installer/pyasl_setup.iss` | Windows | Inno Setup installer script |
