"""
Tests for gui/threads/npy_scanner_worker.py
---------------------------------------------
Integration tests: creates temp directories with .npy files,
runs the scanner, and verifies signals are emitted correctly.
"""
from __future__ import annotations

import os
import tempfile
import zipfile

import numpy as np
import pytest

from pyasl.gui.threads.npy_scanner_worker import (
    NpyExportWorker,
    NpyScannerWorker,
)


@pytest.fixture
def sample_npy_dir(tmp_path):
    """Create a temporary directory with various .npy files."""
    # 1D
    np.save(str(tmp_path / "signal.npy"), np.arange(100, dtype=np.float32))
    # 2D
    np.save(str(tmp_path / "image.npy"), np.random.rand(32, 32))
    # 3D
    np.save(str(tmp_path / "volume.npy"), np.random.rand(8, 8, 8))
    # Nested subdirectory
    sub = tmp_path / "subdir"
    sub.mkdir()
    np.save(str(sub / "nested.npy"), np.array([1, 2, 3]))
    return str(tmp_path)


@pytest.fixture
def corrupt_npy_dir(tmp_path):
    """Create a directory with a corrupt .npy file."""
    corrupt_path = tmp_path / "corrupt.npy"
    corrupt_path.write_bytes(b"this is not a valid npy file")
    # Also a valid one
    np.save(str(tmp_path / "valid.npy"), np.array([1.0, 2.0]))
    return str(tmp_path)


class TestNpyScannerWorker:
    """Tests for the scanner worker (run synchronously via .run())."""

    def test_discovers_all_npy_files(self, sample_npy_dir):
        worker = NpyScannerWorker([sample_npy_dir])
        results = []
        worker.file_visualized.connect(results.append)
        worker.run()  # Run synchronously (not .start())
        assert len(results) == 4  # signal, image, volume, nested

    def test_all_results_have_png(self, sample_npy_dir):
        worker = NpyScannerWorker([sample_npy_dir])
        results = []
        worker.file_visualized.connect(results.append)
        worker.run()
        for r in results:
            assert r["png_bytes"] is not None
            assert r["error"] is None
            assert r["png_bytes"][:4] == b"\x89PNG"

    def test_scan_complete_emits(self, sample_npy_dir):
        worker = NpyScannerWorker([sample_npy_dir])
        final_results = []
        worker.scan_complete.connect(final_results.append)
        worker.run()
        assert len(final_results) == 1
        assert len(final_results[0]) == 4

    def test_handles_corrupt_file_gracefully(self, corrupt_npy_dir):
        worker = NpyScannerWorker([corrupt_npy_dir])
        results = []
        worker.file_visualized.connect(results.append)
        worker.run()
        assert len(results) == 2

        corrupt = [r for r in results if r["metadata"]["filename"] == "corrupt.npy"]
        valid = [r for r in results if r["metadata"]["filename"] == "valid.npy"]

        assert len(corrupt) == 1
        assert corrupt[0]["error"] is not None
        assert corrupt[0]["png_bytes"] is None

        assert len(valid) == 1
        assert valid[0]["error"] is None
        assert valid[0]["png_bytes"] is not None

    def test_empty_directory(self, tmp_path):
        worker = NpyScannerWorker([str(tmp_path)])
        results = []
        worker.scan_complete.connect(results.append)
        worker.run()
        assert len(results) == 1
        assert results[0] == []

    def test_nonexistent_directory(self):
        worker = NpyScannerWorker(["/nonexistent/path"])
        results = []
        worker.scan_complete.connect(results.append)
        worker.run()
        assert len(results) == 1
        assert results[0] == []

    def test_progress_updates(self, sample_npy_dir):
        worker = NpyScannerWorker([sample_npy_dir])
        progress = []
        worker.progress_update.connect(lambda cur, tot: progress.append((cur, tot)))
        worker.run()
        assert len(progress) == 4
        assert progress[-1] == (4, 4)

    def test_multiple_directories(self, tmp_path):
        dir1 = tmp_path / "d1"
        dir2 = tmp_path / "d2"
        dir1.mkdir()
        dir2.mkdir()
        np.save(str(dir1 / "a.npy"), np.array([1]))
        np.save(str(dir2 / "b.npy"), np.array([2]))

        worker = NpyScannerWorker([str(dir1), str(dir2)])
        results = []
        worker.file_visualized.connect(results.append)
        worker.run()
        assert len(results) == 2


class TestNpyExportWorker:
    """Tests for the export worker."""

    def test_export_creates_png_files(self, sample_npy_dir, tmp_path):
        # First scan to get visualization data
        scanner = NpyScannerWorker([sample_npy_dir])
        results = []
        scanner.file_visualized.connect(results.append)
        scanner.run()

        output_dir = str(tmp_path / "export_test")
        os.makedirs(output_dir, exist_ok=True)
        exporter = NpyExportWorker(results, output_dir, create_zip=False)
        export_paths = []
        exporter.export_complete.connect(export_paths.append)
        exporter.run()

        assert len(export_paths) == 1
        viz_dir = export_paths[0]
        pngs = [f for f in os.listdir(viz_dir) if f.endswith(".png")]
        assert len(pngs) == 4

    def test_export_creates_zip(self, sample_npy_dir, tmp_path):
        scanner = NpyScannerWorker([sample_npy_dir])
        results = []
        scanner.file_visualized.connect(results.append)
        scanner.run()

        output_dir = str(tmp_path / "zip_test")
        os.makedirs(output_dir, exist_ok=True)
        exporter = NpyExportWorker(results, output_dir, create_zip=True)
        zip_paths = []
        exporter.zip_complete.connect(zip_paths.append)
        exporter.run()

        assert len(zip_paths) == 1
        assert os.path.isfile(zip_paths[0])
        with zipfile.ZipFile(zip_paths[0], "r") as zf:
            names = zf.namelist()
            assert len(names) == 4
            assert all(n.endswith(".png") for n in names)

    def test_export_skips_errored_files(self, corrupt_npy_dir, tmp_path):
        scanner = NpyScannerWorker([corrupt_npy_dir])
        results = []
        scanner.file_visualized.connect(results.append)
        scanner.run()

        output_dir = str(tmp_path / "skip_test")
        os.makedirs(output_dir, exist_ok=True)
        exporter = NpyExportWorker(results, output_dir, create_zip=False)
        export_paths = []
        exporter.export_complete.connect(export_paths.append)
        exporter.run()

        viz_dir = export_paths[0]
        pngs = [f for f in os.listdir(viz_dir) if f.endswith(".png")]
        # Only valid.npy should produce a PNG, corrupt.npy should be skipped
        assert len(pngs) == 1
