"""
gui/models/batch_state.py
--------------------------
Manages the queue of batch jobs and their status/progress.
Pure data — no Qt widgets.
"""
from __future__ import annotations

import os
import uuid
from typing import Dict, List, Optional


class BatchJob:
    """Data container for a single batch job."""

    __slots__ = (
        "job_id", "label", "data_dir", "config_path",
        "pipeline_type", "status", "duration", "error", "traceback",
    )

    def __init__(
        self,
        data_dir: str,
        config_path: str,
        pipeline_type: str = "legacy",
        job_id: Optional[str] = None,
        label: Optional[str] = None,
    ) -> None:
        self.job_id = job_id or str(uuid.uuid4())[:8]
        self.label = label or os.path.basename(data_dir)
        self.data_dir = data_dir
        self.config_path = config_path
        self.pipeline_type = pipeline_type
        self.status: str = "PENDING"
        self.duration: Optional[float] = None
        self.error: Optional[str] = None
        self.traceback: Optional[str] = None

    def compute_hash(self) -> str:
        import hashlib
        norm_data = os.path.normpath(os.path.abspath(self.data_dir)) if self.data_dir else ""
        norm_cfg = os.path.normpath(os.path.abspath(self.config_path)) if self.config_path else ""
        key = f"{norm_data}|{norm_cfg}|{self.pipeline_type}".encode("utf-8")
        return hashlib.sha256(key).hexdigest()

    def to_table_row(self) -> List[str]:
        """Column values matching ``BATCH_COLUMNS``."""
        return [
            self.job_id,
            self.label,
            self.data_dir,
            os.path.basename(self.config_path),
            self.pipeline_type,
            self.status,
            f"{self.duration:.2f}s" if self.duration else "—",
        ]


class BatchState:
    """Manages the ordered list of batch jobs."""

    def __init__(self) -> None:
        self._jobs: List[BatchJob] = []

    @property
    def jobs(self) -> List[BatchJob]:
        return list(self._jobs)

    @property
    def count(self) -> int:
        return len(self._jobs)

    # -- mutation ----------------------------------------------------------

    def add_job(
        self,
        data_dir: str,
        config_path: str,
        pipeline_type: str = "legacy",
    ) -> BatchJob:
        job = BatchJob(data_dir, config_path, pipeline_type)
        new_hash = job.compute_hash()

        # Duplicate check against pending/running jobs
        for j in self._jobs:
            if j.compute_hash() == new_hash and j.status in ("PENDING", "RUNNING", "RETRYING"):
                raise ValueError(
                    f"Duplicate Job: A job for data directory '{os.path.basename(data_dir)}' "
                    f"and configuration '{os.path.basename(config_path)}' is already in the batch queue."
                )

        self._jobs.append(job)
        return job

    def remove_jobs(self, job_ids: List[str]) -> None:
        self._jobs = [j for j in self._jobs if j.job_id not in job_ids]

    def clear(self) -> None:
        self._jobs.clear()

    def update_status(self, job_id: str, status: str) -> None:
        for j in self._jobs:
            if j.job_id == job_id:
                j.status = status
                break

    def update_duration(self, job_id: str, duration: Optional[float]) -> None:
        for j in self._jobs:
            if j.job_id == job_id:
                j.duration = duration
                break

    def update_error(self, job_id: str, error: Optional[str], traceback: Optional[str]) -> None:
        for j in self._jobs:
            if j.job_id == job_id:
                j.error = error
                j.traceback = traceback
                break

    # -- queries -----------------------------------------------------------

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        for j in self._jobs:
            if j.job_id == job_id:
                return j
        return None

    def progress_summary(self) -> Dict[str, int]:
        total = len(self._jobs)
        completed = sum(1 for j in self._jobs if j.status == "COMPLETED")
        failed = sum(1 for j in self._jobs if j.status == "FAILED")
        done = sum(1 for j in self._jobs if j.status in ("COMPLETED", "FAILED", "ABORTED"))
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "done": done,
            "pending": total - done,
        }
