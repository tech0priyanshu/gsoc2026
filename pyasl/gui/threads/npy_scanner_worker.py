"""
gui/threads/npy_scanner_worker.py
-----------------------------------
Background QThread that scans directories for .npy files,
renders visualizations, and optionally exports them.

Emits Qt signals so the GUI updates from the main thread.
"""
from __future__ import annotations

import os
import zipfile
from typing import Dict, List, Optional

import numpy as np

try:
    from PyQt6.QtCore import QThread, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.utils.npy_visualizer import (
    get_array_metadata,
    render_array_to_png,
    save_png,
)


class NpyScannerWorker(QThread):
    """
    Scans directories for .npy files, renders visualizations,
    and emits results one-by-one for live UI updates.

    Signals
    -------
    file_visualized(dict)
        Per-file result: {path, metadata, png_bytes, error}
    scan_complete(list)
        All results when scanning is finished.
    progress_update(int, int)
        (current_index, total_count) for progress tracking.
    """

    file_visualized = pyqtSignal(dict)
    scan_complete = pyqtSignal(list)
    progress_update = pyqtSignal(int, int)

    def __init__(
        self,
        directories: List[str],
        theme: str = "dark",
        parent=None,
    ):
        super().__init__(parent)
        self._directories = directories
        self._theme = theme

    def run(self):
        """Scan all directories and render each .npy file."""
        # Phase 1: Discover all .npy files
        npy_files: List[str] = []
        for directory in self._directories:
            if not os.path.isdir(directory):
                continue
            for root, _dirs, files in os.walk(directory):
                for fname in sorted(files):
                    if fname.lower().endswith(".npy"):
                        npy_files.append(os.path.join(root, fname))

        total = len(npy_files)
        all_results: List[Dict] = []

        # Phase 2: Load and render each file
        for idx, fpath in enumerate(npy_files):
            result = self._process_file(fpath)
            all_results.append(result)
            self.file_visualized.emit(result)
            self.progress_update.emit(idx + 1, total)

        self.scan_complete.emit(all_results)

    def _process_file(self, fpath: str) -> Dict:
        """
        Load one .npy file, extract metadata, and render to PNG.

        Returns a dict with keys: path, metadata, png_bytes, error.
        On failure, png_bytes is None and error contains the message.
        """
        try:
            arr = np.load(fpath, allow_pickle=False)
            metadata = get_array_metadata(arr, fpath)
            png_bytes = render_array_to_png(arr, fpath, theme=self._theme)
            return {
                "path": fpath,
                "metadata": metadata,
                "png_bytes": png_bytes,
                "error": None,
            }
        except Exception as exc:
            return {
                "path": fpath,
                "metadata": {
                    "filename": os.path.basename(fpath),
                    "filepath": fpath,
                    "shape": None,
                    "dtype": None,
                    "min": None,
                    "max": None,
                    "ndim": None,
                    "description": "Failed to load",
                },
                "png_bytes": None,
                "error": str(exc),
            }


class NpyExportWorker(QThread):
    """
    Exports pre-rendered PNG bytes to disk and optionally
    creates a ZIP archive.

    Signals
    -------
    export_complete(str)
        Path to the output folder.
    zip_complete(str)
        Path to the generated ZIP file.
    error_occurred(str)
        Error message if something fails.
    """

    export_complete = pyqtSignal(str)
    zip_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        visualizations: List[Dict],
        output_dir: str,
        create_zip: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._visualizations = visualizations
        self._output_dir = output_dir
        self._create_zip = create_zip

    def run(self):
        try:
            viz_dir = os.path.join(self._output_dir, "visualizations")
            os.makedirs(viz_dir, exist_ok=True)

            saved_paths: List[str] = []
            for viz in self._visualizations:
                if viz.get("png_bytes") is None:
                    continue
                base = os.path.splitext(viz["metadata"]["filename"])[0]
                out_path = os.path.join(viz_dir, f"{base}.png")

                # Avoid overwriting: add suffix if needed
                counter = 1
                final_path = out_path
                while os.path.exists(final_path):
                    final_path = os.path.join(
                        viz_dir, f"{base}_{counter}.png"
                    )
                    counter += 1

                save_png(viz["png_bytes"], final_path)
                saved_paths.append(final_path)

            self.export_complete.emit(viz_dir)

            if self._create_zip and saved_paths:
                zip_path = os.path.join(
                    self._output_dir, "visualizations.zip"
                )
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for sp in saved_paths:
                        zf.write(sp, os.path.basename(sp))
                self.zip_complete.emit(zip_path)

        except Exception as exc:
            self.error_occurred.emit(str(exc))
