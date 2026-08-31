"""
gui/models/cache_manager.py
-----------------------------
Processing-result cache for PyASL GUI.

Avoids re-processing files that have already been processed by
caching results keyed on a SHA-256 hash of the input data directory
contents and pipeline configuration file.

Pure-Python — no Qt dependency.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages a file-based cache of processing results.

    Cache layout::

        <cache_dir>/
        └── <sha256_hash>/
            ├── result.json      # serialized processing result
            └── metadata.json    # original paths, timestamp, hash
    """

    def __init__(self, cache_dir: str) -> None:
        self._cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self._cache_dir, exist_ok=True)

    @property
    def cache_dir(self) -> str:
        return self._cache_dir

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    @staticmethod
    def compute_hash(data_dir: str, config_path: str) -> str:
        """
        Compute a SHA-256 hash representing the combination of
        *data_dir* contents and *config_path* content.

        For efficiency, we hash:
        - The sorted list of filenames + sizes in ``data_dir`` (not full
          content, which could be many GB of NIfTI data).
        - The full content of ``config_path`` (YAML configs are small).

        This gives a fast, deterministic fingerprint that changes when
        files are added/removed/resized in the data directory or when
        the pipeline configuration changes.
        """
        h = hashlib.sha256()

        # Hash data directory structure (names + sizes)
        if os.path.isdir(data_dir):
            entries = []
            for root, dirs, files in os.walk(data_dir):
                dirs.sort()
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, data_dir)
                    try:
                        size = os.path.getsize(fpath)
                    except OSError:
                        size = 0
                    entries.append(f"{rel}:{size}")
            for entry in entries:
                h.update(entry.encode("utf-8"))

        # Hash config file content
        if os.path.isfile(config_path):
            try:
                with open(config_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
            except OSError:
                pass

        return h.hexdigest()

    # ------------------------------------------------------------------
    # Cache operations
    # ------------------------------------------------------------------

    def get_cached_result(
        self, data_dir: str, config_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        Look up a cached result for the given inputs.

        Returns the result dict if found and valid, or ``None``.
        """
        cache_key = self.compute_hash(data_dir, config_path)
        entry_dir = os.path.join(self._cache_dir, cache_key)
        result_path = os.path.join(entry_dir, "result.json")

        if not os.path.isfile(result_path):
            return None

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result = json.load(f)
            logger.debug("Cache HIT for %s (key=%s…)", data_dir, cache_key[:12])
            return result
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted cache entry %s — removing.", cache_key[:12])
            self.remove_entry(cache_key)
            return None

    def store_result(
        self,
        data_dir: str,
        config_path: str,
        result: Dict[str, Any],
    ) -> str:
        """
        Store a processing result in the cache.

        Returns the cache key (SHA-256 hex string).
        """
        cache_key = self.compute_hash(data_dir, config_path)
        entry_dir = os.path.join(self._cache_dir, cache_key)
        os.makedirs(entry_dir, exist_ok=True)

        # Write result
        result_path = os.path.join(entry_dir, "result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # Write metadata
        metadata = {
            "data_dir": data_dir,
            "config_path": config_path,
            "cache_key": cache_key,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_path = os.path.join(entry_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.debug("Cached result for %s (key=%s…)", data_dir, cache_key[:12])
        return cache_key

    def is_cached(self, data_dir: str, config_path: str) -> bool:
        """Check whether a cached result exists for the given inputs."""
        cache_key = self.compute_hash(data_dir, config_path)
        result_path = os.path.join(self._cache_dir, cache_key, "result.json")
        return os.path.isfile(result_path)

    def remove_entry(self, cache_key: str) -> None:
        """Remove a single cache entry by its hash key."""
        entry_dir = os.path.join(self._cache_dir, cache_key)
        if os.path.isdir(entry_dir):
            shutil.rmtree(entry_dir, ignore_errors=True)

    def clear_cache(self) -> None:
        """Remove all cached entries."""
        if os.path.isdir(self._cache_dir):
            shutil.rmtree(self._cache_dir, ignore_errors=True)
            os.makedirs(self._cache_dir, exist_ok=True)
        logger.info("Cache cleared.")

    def list_entries(self) -> list[Dict[str, Any]]:
        """List all cache entries with their metadata."""
        entries = []
        if not os.path.isdir(self._cache_dir):
            return entries
        for name in os.listdir(self._cache_dir):
            meta_path = os.path.join(self._cache_dir, name, "metadata.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        entries.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass
        return entries
