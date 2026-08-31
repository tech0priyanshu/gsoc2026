"""
Tests for gui/utils/npy_visualizer.py
--------------------------------------
Verifies rendering of 1D, 2D, 3D, 4D+ arrays to PNG bytes,
metadata extraction, and error handling.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from pyasl.gui.utils.npy_visualizer import (
    get_array_metadata,
    render_array_to_png,
    save_png,
)


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

class TestGetArrayMetadata:

    def test_1d_metadata(self):
        arr = np.arange(100, dtype=np.float32)
        meta = get_array_metadata(arr, "signal.npy")
        assert meta["filename"] == "signal.npy"
        assert meta["shape"] == (100,)
        assert meta["dtype"] == "float32"
        assert meta["ndim"] == 1
        assert meta["min"] == 0.0
        assert meta["max"] == 99.0
        assert "1D" in meta["description"]

    def test_2d_metadata(self):
        arr = np.random.rand(64, 64).astype(np.float64)
        meta = get_array_metadata(arr, "image.npy")
        assert meta["ndim"] == 2
        assert meta["shape"] == (64, 64)
        assert "2D" in meta["description"]

    def test_3d_metadata(self):
        arr = np.zeros((10, 20, 30), dtype=np.int16)
        meta = get_array_metadata(arr, "volume.npy")
        assert meta["ndim"] == 3
        assert meta["shape"] == (10, 20, 30)
        assert "3D" in meta["description"]

    def test_4d_metadata(self):
        arr = np.ones((5, 10, 10, 3), dtype=np.uint8)
        meta = get_array_metadata(arr, "timeseries.npy")
        assert meta["ndim"] == 4
        assert "4D" in meta["description"]

    def test_metadata_with_nan(self):
        arr = np.array([1.0, np.nan, 3.0])
        meta = get_array_metadata(arr, "nan_data.npy")
        assert meta["min"] == 1.0
        assert meta["max"] == 3.0

    def test_full_path_extracts_basename(self):
        arr = np.array([1, 2, 3])
        meta = get_array_metadata(arr, "/some/deep/path/data.npy")
        assert meta["filename"] == "data.npy"
        assert meta["filepath"] == "/some/deep/path/data.npy"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class TestRenderArrayToPng:

    def test_1d_renders_png(self):
        arr = np.sin(np.linspace(0, 4 * np.pi, 200))
        result = render_array_to_png(arr, "sine.npy")
        assert isinstance(result, bytes)
        assert len(result) > 100
        # PNG magic bytes
        assert result[:4] == b"\x89PNG"

    def test_2d_renders_png(self):
        arr = np.random.rand(32, 32).astype(np.float32)
        result = render_array_to_png(arr, "heatmap.npy")
        assert result[:4] == b"\x89PNG"

    def test_3d_renders_png(self):
        arr = np.random.rand(16, 16, 16).astype(np.float64)
        result = render_array_to_png(arr, "volume.npy")
        assert result[:4] == b"\x89PNG"

    def test_4d_renders_png(self):
        arr = np.random.rand(8, 8, 8, 4).astype(np.float32)
        result = render_array_to_png(arr, "4d_data.npy")
        assert result[:4] == b"\x89PNG"

    def test_5d_renders_png(self):
        arr = np.random.rand(4, 4, 4, 2, 3).astype(np.float32)
        result = render_array_to_png(arr, "5d_data.npy")
        assert result[:4] == b"\x89PNG"

    def test_empty_array_raises(self):
        arr = np.array([])
        with pytest.raises(ValueError, match="empty"):
            render_array_to_png(arr, "empty.npy")

    def test_single_element_1d(self):
        arr = np.array([42.0])
        result = render_array_to_png(arr, "single.npy")
        assert result[:4] == b"\x89PNG"

    def test_integer_array(self):
        arr = np.arange(50, dtype=np.int32)
        result = render_array_to_png(arr, "integers.npy")
        assert result[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# Save to disk
# ---------------------------------------------------------------------------

class TestSavePng:

    def test_save_creates_file(self, tmp_path):
        arr = np.random.rand(16, 16)
        png_bytes = render_array_to_png(arr, "test.npy")
        out_path = str(tmp_path / "output" / "test.png")
        result_path = save_png(png_bytes, out_path)
        assert os.path.isfile(result_path)
        with open(result_path, "rb") as f:
            assert f.read(4) == b"\x89PNG"

    def test_save_creates_directories(self, tmp_path):
        arr = np.random.rand(8, 8)
        png_bytes = render_array_to_png(arr, "nested.npy")
        out_path = str(tmp_path / "a" / "b" / "c" / "nested.png")
        result_path = save_png(png_bytes, out_path)
        assert os.path.isfile(result_path)
