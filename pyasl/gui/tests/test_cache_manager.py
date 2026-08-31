"""
Tests for CacheManager.

Covers hash computation consistency, cache hit/miss, storage,
invalidation on file change, and cleanup.
"""
from __future__ import annotations

import json
import os

import pytest

from pyasl.gui.models.cache_manager import CacheManager


@pytest.fixture
def cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cd = tmp_path / "cache"
    cd.mkdir()
    return str(cd)


@pytest.fixture
def cache(cache_dir):
    return CacheManager(cache_dir)


@pytest.fixture
def sample_data(tmp_path):
    """Create sample data_dir and config_path for testing."""
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    # Create some files in data_dir
    with open(os.path.join(data_dir, "file1.nii"), "wb") as f:
        f.write(b"x" * 100)
    with open(os.path.join(data_dir, "file2.nii"), "wb") as f:
        f.write(b"y" * 200)

    config_path = str(tmp_path / "config.yaml")
    with open(config_path, "w") as f:
        f.write("steps:\n  - module: BrukerLoader\n")

    return data_dir, config_path


class TestHashing:
    def test_deterministic(self, sample_data):
        data_dir, config_path = sample_data
        h1 = CacheManager.compute_hash(data_dir, config_path)
        h2 = CacheManager.compute_hash(data_dir, config_path)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length

    def test_different_config_produces_different_hash(self, sample_data, tmp_path):
        data_dir, config_path = sample_data

        config2 = str(tmp_path / "config2.yaml")
        with open(config2, "w") as f:
            f.write("steps:\n  - module: NIfTILoader\n")

        h1 = CacheManager.compute_hash(data_dir, config_path)
        h2 = CacheManager.compute_hash(data_dir, config2)
        assert h1 != h2

    def test_different_data_produces_different_hash(self, sample_data, tmp_path):
        data_dir, config_path = sample_data

        data2 = str(tmp_path / "data2")
        os.makedirs(data2, exist_ok=True)
        with open(os.path.join(data2, "different.nii"), "wb") as f:
            f.write(b"z" * 300)

        h1 = CacheManager.compute_hash(data_dir, config_path)
        h2 = CacheManager.compute_hash(data2, config_path)
        assert h1 != h2

    def test_nonexistent_paths_produce_stable_hash(self):
        h = CacheManager.compute_hash("/nonexistent/dir", "/nonexistent/file")
        assert isinstance(h, str)
        assert len(h) == 64

    def test_file_size_change_detected(self, sample_data):
        data_dir, config_path = sample_data
        h1 = CacheManager.compute_hash(data_dir, config_path)

        # Change size of file1
        with open(os.path.join(data_dir, "file1.nii"), "wb") as f:
            f.write(b"x" * 999)

        h2 = CacheManager.compute_hash(data_dir, config_path)
        assert h1 != h2

    def test_new_file_in_data_dir_detected(self, sample_data):
        data_dir, config_path = sample_data
        h1 = CacheManager.compute_hash(data_dir, config_path)

        with open(os.path.join(data_dir, "file3.nii"), "wb") as f:
            f.write(b"new_file")

        h2 = CacheManager.compute_hash(data_dir, config_path)
        assert h1 != h2


class TestCacheHitMiss:
    def test_miss_on_empty_cache(self, cache, sample_data):
        data_dir, config_path = sample_data
        result = cache.get_cached_result(data_dir, config_path)
        assert result is None

    def test_is_cached_false_on_empty(self, cache, sample_data):
        data_dir, config_path = sample_data
        assert cache.is_cached(data_dir, config_path) is False

    def test_store_and_hit(self, cache, sample_data):
        data_dir, config_path = sample_data
        result = {"job_id": "test1", "status": "COMPLETED", "duration": 2.5}

        cache.store_result(data_dir, config_path, result)
        assert cache.is_cached(data_dir, config_path) is True

        restored = cache.get_cached_result(data_dir, config_path)
        assert restored is not None
        assert restored["job_id"] == "test1"
        assert restored["status"] == "COMPLETED"

    def test_cache_invalidation_on_data_change(self, cache, sample_data):
        data_dir, config_path = sample_data
        cache.store_result(data_dir, config_path, {"status": "COMPLETED"})
        assert cache.is_cached(data_dir, config_path) is True

        # Modify a file in data_dir → hash changes → cache miss
        with open(os.path.join(data_dir, "file1.nii"), "wb") as f:
            f.write(b"modified_content")

        assert cache.is_cached(data_dir, config_path) is False
        assert cache.get_cached_result(data_dir, config_path) is None


class TestCacheOperations:
    def test_store_creates_metadata(self, cache, sample_data):
        data_dir, config_path = sample_data
        key = cache.store_result(data_dir, config_path, {"status": "ok"})

        meta_path = os.path.join(cache.cache_dir, key, "metadata.json")
        assert os.path.isfile(meta_path)

        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["data_dir"] == data_dir
        assert meta["config_path"] == config_path
        assert meta["cache_key"] == key

    def test_remove_entry(self, cache, sample_data):
        data_dir, config_path = sample_data
        key = cache.store_result(data_dir, config_path, {"status": "ok"})
        assert cache.is_cached(data_dir, config_path)

        cache.remove_entry(key)
        assert cache.is_cached(data_dir, config_path) is False

    def test_clear_cache(self, cache, sample_data):
        data_dir, config_path = sample_data
        cache.store_result(data_dir, config_path, {"status": "ok"})
        cache.clear_cache()

        assert cache.is_cached(data_dir, config_path) is False
        assert os.path.isdir(cache.cache_dir)  # dir recreated

    def test_list_entries(self, cache, sample_data, tmp_path):
        d1, c1 = sample_data

        d2 = str(tmp_path / "data2")
        os.makedirs(d2)
        c2 = str(tmp_path / "config2.yaml")
        with open(c2, "w") as f:
            f.write("steps: []\n")

        cache.store_result(d1, c1, {"job": 1})
        cache.store_result(d2, c2, {"job": 2})

        entries = cache.list_entries()
        assert len(entries) == 2
        keys = {e["cache_key"] for e in entries}
        assert len(keys) == 2  # distinct hashes

    def test_corrupted_result_returns_none_and_removes(self, cache, sample_data):
        data_dir, config_path = sample_data
        key = cache.store_result(data_dir, config_path, {"status": "ok"})

        # Corrupt the result file
        result_path = os.path.join(cache.cache_dir, key, "result.json")
        with open(result_path, "w") as f:
            f.write("{{{corrupted")

        result = cache.get_cached_result(data_dir, config_path)
        assert result is None
        # Entry should be cleaned up
        assert not os.path.isdir(os.path.join(cache.cache_dir, key))
