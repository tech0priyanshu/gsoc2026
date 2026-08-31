"""
gui/models/results_state.py
--------------------------
Manages the list of generated outputs/results from tasks
like Pipeline or Batch executions.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


class NpyVisualization:
    """Data container for one .npy file visualization."""

    __slots__ = ("file_path", "metadata", "png_bytes", "error")

    def __init__(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        png_bytes: Optional[bytes] = None,
        error: Optional[str] = None,
    ) -> None:
        self.file_path = file_path
        self.metadata = metadata      # {filename, shape, dtype, min, max, ndim, description}
        self.png_bytes = png_bytes    # PNG image data (None on error)
        self.error = error            # Error message (None on success)

    @property
    def is_valid(self) -> bool:
        return self.png_bytes is not None and self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "metadata": self.metadata,
            "has_image": self.png_bytes is not None,
            "error": self.error,
        }


class ResultItem:
    """Data container for a single execution result."""

    __slots__ = (
        "id", "name", "type", "status", "timestamp", "summary",
        "full_output", "visualizations", "data_dirs",
    )

    def __init__(
        self,
        name: str,
        result_type: str,
        status: str,
        summary: str,
        full_output: str,
        timestamp: Optional[str] = None,
        data_dirs: Optional[List[str]] = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = result_type  # "pipeline" or "batch"
        self.status = status     # "COMPLETED", "FAILED"
        self.summary = summary
        self.full_output = full_output
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.visualizations: List[NpyVisualization] = []
        self.data_dirs: List[str] = data_dirs or []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "full_output": self.full_output,
            "data_dirs": self.data_dirs,
            "visualizations_count": len(self.visualizations),
        }


class ResultsState:
    """Manages the ordered list of results."""

    def __init__(self) -> None:
        self._results: List[ResultItem] = []

    @property
    def results(self) -> List[ResultItem]:
        return list(self._results)

    @property
    def count(self) -> int:
        return len(self._results)

    def add_result(self, item: ResultItem) -> None:
        # Prepend so the newest results are at the top
        self._results.insert(0, item)

    def remove_result(self, result_id: str) -> None:
        self._results = [r for r in self._results if r.id != result_id]

    def clear(self) -> None:
        self._results.clear()

    def get_result(self, result_id: str) -> Optional[ResultItem]:
        for r in self._results:
            if r.id == result_id:
                return r
        return None
