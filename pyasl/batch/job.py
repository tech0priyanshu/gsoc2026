"""
batch/job.py
------------
Data classes for describing and tracking batch jobs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
import time
import uuid


class BatchStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CACHED = "CACHED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


@dataclass
class BatchJob:
    """
    Describes one dataset to process in a batch run.

    Parameters
    ----------
    data_dir      : Path to the input data directory.
    config_path   : Path to the YAML pipeline configuration.
    pipeline_type : "dag" to use the DAG engine; "legacy" to use run_pipeline.
    job_id        : Unique identifier (auto-generated if not supplied).
    label         : Optional human-readable label shown in the GUI.
    """
    data_dir: str
    config_path: str
    pipeline_type: str = "legacy"   # "dag" | "legacy"
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    label: str = ""
    status: BatchStatus = BatchStatus.PENDING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "label": self.label or self.job_id,
            "data_dir": self.data_dir,
            "config_path": self.config_path,
            "pipeline_type": self.pipeline_type,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "error": self.error,
        }


@dataclass
class BatchResult:
    """Outcome of a single batch job."""
    job_id: str
    status: BatchStatus
    data_dir: str
    config_path: str
    start_time: float
    end_time: float
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    traceback: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "data_dir": self.data_dir,
            "config_path": self.config_path,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": round(self.duration, 3),
            "error": self.error,
            "traceback": self.traceback,
        }
