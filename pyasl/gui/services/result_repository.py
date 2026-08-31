"""
gui/services/result_repository.py
-----------------------------------
Persistence layer for ``ProcessedResult`` objects.

Stores results as JSON metadata + .npy array files in
the workspace ``results/`` directory.

Pure Python — no Qt dependency.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pyasl.gui.models.result_data import ProcessedResult, ResultSummary
from pyasl.gui.models.result_ui_state import ResultUIState

logger = logging.getLogger(__name__)


class ResultRepository:
    """
    File-based persistence for processed results.

    Storage layout::

        <results_dir>/
        ├── <result_id>/
        │   ├── result.json        # ProcessedResult serialized
        │   ├── ui_state.json      # ResultUIState serialized
        │   └── arrays/            # .npy files (copies or symlinks)
        ├── <result_id>/
        │   └── ...
        └── index.json             # Quick-access result listing
    """

    INDEX_FILE = "index.json"

    def __init__(self, results_dir: str) -> None:
        self._dir = results_dir
        os.makedirs(self._dir, exist_ok=True)
        self._ensure_index()

    @property
    def results_dir(self) -> str:
        return self._dir

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(
        self,
        result: ProcessedResult,
        ui_state: Optional[ResultUIState] = None,
    ) -> str:
        """
        Persist a result.  Returns the result_id.

        Never silently overwrites — creates a versioned directory if
        the result_id already exists.
        """
        result_dir = os.path.join(self._dir, result.result_id)

        # Avoid overwriting
        if os.path.isdir(result_dir):
            # Update the existing result
            result.updated_at = datetime.now(timezone.utc).isoformat()
        else:
            os.makedirs(result_dir, exist_ok=True)

        # Write metadata
        result_path = os.path.join(result_dir, "result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

        # Write UI state
        if ui_state is not None:
            ui_path = os.path.join(result_dir, "ui_state.json")
            with open(ui_path, "w", encoding="utf-8") as f:
                json.dump(ui_state.to_dict(), f, indent=2, ensure_ascii=False)

        # Update index
        self._update_index(result)

        logger.info("Result saved: %s → %s", result.result_id, result_dir)
        return result.result_id

    def save_as(
        self,
        result: ProcessedResult,
        new_name: str,
        ui_state: Optional[ResultUIState] = None,
    ) -> str:
        """
        Save a copy of the result with a new name and new ID.
        """
        import uuid
        new_result = ProcessedResult.from_dict(result.to_dict())
        new_result.result_id = str(uuid.uuid4())
        new_result.name = new_name
        new_result.created_at = datetime.now(timezone.utc).isoformat()
        new_result.updated_at = new_result.created_at
        # Re-attach entries with the same data references
        new_result.entries = list(result.entries)
        return self.save(new_result, ui_state)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, result_id: str) -> Optional[ProcessedResult]:
        """Load a result by ID.  Returns None if not found."""
        result_dir = os.path.join(self._dir, result_id)
        result_path = os.path.join(result_dir, "result.json")

        if not os.path.isfile(result_path):
            logger.warning("Result not found: %s", result_id)
            return None

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ProcessedResult.from_dict(data)
        except Exception as exc:
            logger.error("Failed to load result %s: %s", result_id, exc)
            return None

    def load_ui_state(self, result_id: str) -> Optional[ResultUIState]:
        """Load saved UI state for a result."""
        ui_path = os.path.join(self._dir, result_id, "ui_state.json")
        if not os.path.isfile(ui_path):
            return None
        try:
            with open(ui_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ResultUIState.from_dict(data)
        except Exception as exc:
            logger.error("Failed to load UI state for %s: %s", result_id, exc)
            return None

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, result_id: str) -> bool:
        """Delete a result and its directory."""
        result_dir = os.path.join(self._dir, result_id)
        if not os.path.isdir(result_dir):
            return False
        try:
            shutil.rmtree(result_dir)
            self._remove_from_index(result_id)
            logger.info("Result deleted: %s", result_id)
            return True
        except Exception as exc:
            logger.error("Failed to delete result %s: %s", result_id, exc)
            return False

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_all(self) -> List[ResultSummary]:
        """Return summaries of all saved results, newest first."""
        index = self._load_index()
        summaries = []
        for entry in index.get("results", []):
            summaries.append(ResultSummary(
                result_id=entry.get("result_id", ""),
                name=entry.get("name", ""),
                source_reference=entry.get("source_reference", ""),
                created_at=entry.get("created_at", ""),
                entry_count=entry.get("entry_count", 0),
                asl_version=entry.get("asl_version", ""),
                has_errors=entry.get("has_errors", False),
            ))
        # Sort newest first
        summaries.sort(key=lambda s: s.created_at, reverse=True)
        return summaries

    def exists(self, result_id: str) -> bool:
        """Check if a result ID exists."""
        result_dir = os.path.join(self._dir, result_id)
        return os.path.isdir(result_dir)

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _ensure_index(self) -> None:
        """Create index.json if it doesn't exist."""
        idx_path = os.path.join(self._dir, self.INDEX_FILE)
        if not os.path.isfile(idx_path):
            with open(idx_path, "w", encoding="utf-8") as f:
                json.dump({"results": []}, f, indent=2)

    def _load_index(self) -> Dict:
        idx_path = os.path.join(self._dir, self.INDEX_FILE)
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"results": []}

    def _save_index(self, index: Dict) -> None:
        idx_path = os.path.join(self._dir, self.INDEX_FILE)
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def _update_index(self, result: ProcessedResult) -> None:
        """Add or update a result entry in the index."""
        index = self._load_index()
        entries = index.get("results", [])

        # Remove existing entry with same ID
        entries = [e for e in entries if e.get("result_id") != result.result_id]

        # Add new entry
        entries.append({
            "result_id": result.result_id,
            "name": result.name,
            "source_reference": result.source_reference,
            "created_at": result.created_at,
            "entry_count": result.entry_count,
            "asl_version": result.processing_metadata.asl_version,
            "has_errors": result.has_errors,
        })

        index["results"] = entries
        self._save_index(index)

    def _remove_from_index(self, result_id: str) -> None:
        """Remove a result from the index."""
        index = self._load_index()
        entries = index.get("results", [])
        index["results"] = [e for e in entries if e.get("result_id") != result_id]
        self._save_index(index)
