"""
gui/models/session_manager.py
-------------------------------
Persistent session management for PyASL GUI.

Handles saving/loading of workspace state (batch jobs, pipeline graph,
settings) to a ``session.json`` file so the application can restore its
previous state on restart.

Pure-Python — no Qt dependency.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Current schema version — bump when session format changes
SESSION_VERSION = 1


class SessionManager:
    """
    Manages persistent session state for the PyASL GUI.

    Workspace layout::

        <workspace_root>/
        ├── uploads/         # reserved for future file-copy workflow
        ├── cache/           # CacheManager storage
        ├── logs/            # application logs
        └── session.json     # this manager's data
    """

    def __init__(self, workspace_root: Optional[str] = None) -> None:
        if workspace_root is None:
            workspace_root = os.path.join(
                os.path.expanduser("~"), ".pyasl_workspace"
            )
        self._root = os.path.abspath(workspace_root)
        self._session_path = os.path.join(self._root, "session.json")

        # In-memory session data
        self._data: Dict[str, Any] = self._empty_session()

        # Ensure workspace directories exist
        self._init_workspace()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def workspace_root(self) -> str:
        return self._root

    @property
    def cache_dir(self) -> str:
        return os.path.join(self._root, "cache")

    @property
    def uploads_dir(self) -> str:
        return os.path.join(self._root, "uploads")

    @property
    def logs_dir(self) -> str:
        return os.path.join(self._root, "logs")

    @property
    def session_path(self) -> str:
        return self._session_path

    @property
    def data(self) -> Dict[str, Any]:
        """Current session data (read-only view)."""
        return dict(self._data)

    # ------------------------------------------------------------------
    # Workspace initialisation
    # ------------------------------------------------------------------

    def _init_workspace(self) -> None:
        """Create workspace directories if they don't exist."""
        for subdir in ("uploads", "cache", "logs"):
            os.makedirs(os.path.join(self._root, subdir), exist_ok=True)

    # ------------------------------------------------------------------
    # Empty session template
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_session() -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "version": SESSION_VERSION,
            "created_at": now,
            "last_opened": now,
            "workspace": "",
            "batch_jobs": [],
            "execution_history": {},
            "pipeline": {"nodes": []},
            "settings": {
                "log_path": "",
                "default_workers": 2,
                "theme": "dark",
            },
        }

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist current in-memory session to ``session.json``."""
        self._data["last_opened"] = datetime.now(timezone.utc).isoformat()
        self._data["workspace"] = self._root
        try:
            tmp_path = self._session_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            # Atomic rename (best-effort on Windows)
            shutil.move(tmp_path, self._session_path)
            logger.debug("Session saved to %s", self._session_path)
        except Exception:
            logger.exception("Failed to save session")

    # ------------------------------------------------------------------
    # Load & validate
    # ------------------------------------------------------------------

    def load(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Load session from disk.

        Returns
        -------
        (success, missing_jobs)
            *success* is ``True`` when a valid session was restored.
            *missing_jobs* contains job dicts whose ``data_dir`` or
            ``config_path`` no longer exist on disk.
        """
        if not os.path.isfile(self._session_path):
            logger.info("No session.json found — starting fresh.")
            self._data = self._empty_session()
            return False, []

        try:
            with open(self._session_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted session.json — starting fresh.")
            self._data = self._empty_session()
            return False, []

        if not isinstance(raw, dict):
            logger.warning("session.json is not a dict — starting fresh.")
            self._data = self._empty_session()
            return False, []

        # Version check
        version = raw.get("version", 0)
        if version != SESSION_VERSION:
            migrated = self._migrate(raw, version)
            if migrated is None:
                logger.warning(
                    "Cannot migrate session v%s → v%s — starting fresh.",
                    version, SESSION_VERSION,
                )
                self._data = self._empty_session()
                return False, []
            raw = migrated

        # Validate batch job file references
        valid_jobs: List[Dict[str, Any]] = []
        missing_jobs: List[Dict[str, Any]] = []

        for job in raw.get("batch_jobs", []):
            data_dir = job.get("data_dir", "")
            config_path = job.get("config_path", "")
            data_ok = os.path.isdir(data_dir) if data_dir else False
            config_ok = os.path.isfile(config_path) if config_path else False
            if data_ok and config_ok:
                valid_jobs.append(job)
            else:
                missing_jobs.append(job)

        raw["batch_jobs"] = valid_jobs
        self._data = raw
        self._data["last_opened"] = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Session loaded: %d valid jobs, %d missing.",
            len(valid_jobs), len(missing_jobs),
        )
        return True, missing_jobs

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    @staticmethod
    def _migrate(
        raw: Dict[str, Any], from_version: int
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to migrate session data from *from_version* to current.

        Returns the migrated dict, or ``None`` if migration is impossible.
        """
        # Currently only v1 exists; future migrations go here
        # e.g. if from_version == 0: ...
        return None

    # ------------------------------------------------------------------
    # Batch jobs
    # ------------------------------------------------------------------

    def set_batch_jobs(self, jobs_data: List[Dict[str, Any]]) -> None:
        """Replace the stored batch jobs list and auto-save."""
        self._data["batch_jobs"] = jobs_data
        self.save()

    def get_batch_jobs(self) -> List[Dict[str, Any]]:
        return list(self._data.get("batch_jobs", []))

    # ------------------------------------------------------------------
    # Execution history
    # ------------------------------------------------------------------

    def set_execution_history(self, history_data: Dict[str, Any]) -> None:
        """Replace the stored execution history and auto-save."""
        self._data["execution_history"] = history_data
        self.save()

    def get_execution_history(self) -> Dict[str, Any]:
        return dict(self._data.get("execution_history", {}))

    # ------------------------------------------------------------------
    # Pipeline state
    # ------------------------------------------------------------------

    def set_pipeline(self, pipeline_data: Dict[str, Any]) -> None:
        """Replace the stored pipeline state and auto-save."""
        self._data["pipeline"] = pipeline_data
        self.save()

    def get_pipeline(self) -> Dict[str, Any]:
        return dict(self._data.get("pipeline", {"nodes": []}))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def set_settings(self, settings: Dict[str, Any]) -> None:
        """Replace stored settings and auto-save."""
        self._data["settings"] = settings
        self.save()

    def get_settings(self) -> Dict[str, Any]:
        return dict(self._data.get("settings", {}))

    def update_setting(self, key: str, value: Any) -> None:
        """Update a single setting value and auto-save."""
        if "settings" not in self._data:
            self._data["settings"] = {}
        self._data["settings"][key] = value
        self.save()

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Discard current session and start fresh."""
        self._data = self._empty_session()
        if os.path.isfile(self._session_path):
            try:
                os.remove(self._session_path)
            except OSError:
                pass
        self.save()

    # ------------------------------------------------------------------
    # Session existence check
    # ------------------------------------------------------------------

    def session_exists(self) -> bool:
        """Return ``True`` if a session.json file exists on disk."""
        return os.path.isfile(self._session_path)
