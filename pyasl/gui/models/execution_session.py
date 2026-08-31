"""
gui/models/execution_session.py
---------------------------------
Shared execution state consumed by both BatchPanelView and MonitorPanelView.

Acts as the **single source of truth** for the current (or most recent)
batch execution.  BatchController writes to it; Monitor and Batch views
subscribe to its signals.

Pure QObject — no widgets.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

try:
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

logger = logging.getLogger(__name__)


class ExecutionSession(QObject):
    """
    Shared execution session model.

    Signals
    -------
    execution_started(int)
        Emitted when a new batch run begins.  Argument: total_jobs.
    execution_completed()
        Emitted when the batch run finishes (all jobs done).
    execution_aborted()
        Emitted when the user aborts mid-run.
    job_started(str, str)
        (job_id, label) — a job transitions to RUNNING.
    job_completed(str, float)
        (job_id, duration) — a job finishes successfully.
    job_failed(str, str)
        (job_id, error_message) — a job fails.
    job_aborted(str)
        (job_id,) — a job is cancelled.
    job_cached(str)
        (job_id,) — a job was served from cache.
    progress_updated(int, int, int, int)
        (total, running, completed, failed) counters.
    log_entry(str)
        A JSON-encoded log string for the live log terminal.
    timeline_event(str, str)
        (job_id, status) — feeds the NodeTimelineWidget.
    stats_updated(dict)
        Full statistics dictionary for summary panels.
    """

    execution_started = pyqtSignal(int)
    execution_completed = pyqtSignal()
    execution_aborted = pyqtSignal()
    job_started = pyqtSignal(str, str)
    job_completed = pyqtSignal(str, float)
    job_failed = pyqtSignal(str, str)
    job_aborted = pyqtSignal(str)
    job_cached = pyqtSignal(str)
    progress_updated = pyqtSignal(int, int, int, int)
    log_entry = pyqtSignal(str)
    timeline_event = pyqtSignal(str, str)
    stats_updated = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Execution state
        self._is_running: bool = False
        self._was_aborted: bool = False
        self._total_jobs: int = 0
        self._running_jobs: int = 0
        self._completed_jobs: int = 0
        self._failed_jobs: int = 0
        self._cached_jobs: int = 0
        self._start_time: float = 0.0
        self._end_time: float = 0.0

        # Current job tracking
        self._current_job_id: Optional[str] = None
        self._current_job_label: Optional[str] = None

        # Per-job data
        self._job_statuses: Dict[str, str] = {}          # job_id → status
        self._job_labels: Dict[str, str] = {}             # job_id → label
        self._job_durations: Dict[str, float] = {}        # job_id → duration
        self._job_errors: Dict[str, str] = {}             # job_id → error

        # Timeline & logs
        self._timeline_events: List[Dict[str, Any]] = []  # {job_id, status, timestamp}
        self._log_entries: List[str] = []                  # JSON strings

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def was_aborted(self) -> bool:
        return self._was_aborted

    @property
    def total_jobs(self) -> int:
        return self._total_jobs

    @property
    def running_jobs(self) -> int:
        return self._running_jobs

    @property
    def completed_jobs(self) -> int:
        return self._completed_jobs

    @property
    def failed_jobs(self) -> int:
        return self._failed_jobs

    @property
    def cached_jobs(self) -> int:
        return self._cached_jobs

    @property
    def start_time(self) -> float:
        return self._start_time

    @property
    def elapsed_duration(self) -> float:
        if self._start_time <= 0:
            return 0.0
        end = self._end_time if self._end_time > 0 else time.time()
        return end - self._start_time

    @property
    def current_job_id(self) -> Optional[str]:
        return self._current_job_id

    @property
    def current_job_label(self) -> Optional[str]:
        return self._current_job_label

    @property
    def job_statuses(self) -> Dict[str, str]:
        return dict(self._job_statuses)

    @property
    def timeline_events(self) -> List[Dict[str, Any]]:
        return list(self._timeline_events)

    @property
    def log_entries(self) -> List[str]:
        return list(self._log_entries)

    @property
    def success_rate(self) -> float:
        done = self._completed_jobs + self._failed_jobs
        if done == 0:
            return 0.0
        return (self._completed_jobs / done) * 100.0

    @property
    def has_data(self) -> bool:
        """True if there is any execution data to display."""
        return self._total_jobs > 0 or len(self._timeline_events) > 0

    # ------------------------------------------------------------------
    # Lifecycle — begin / finalize / abort
    # ------------------------------------------------------------------

    def begin(self, total_jobs: int) -> None:
        """
        Start a new execution session.  Resets all previous state.

        Parameters
        ----------
        total_jobs : int
            Number of jobs in this batch (including cached).
        """
        logger.info("[session] begin: total_jobs=%d", total_jobs)

        # Reset
        self._is_running = True
        self._was_aborted = False
        self._total_jobs = total_jobs
        self._running_jobs = 0
        self._completed_jobs = 0
        self._failed_jobs = 0
        self._cached_jobs = 0
        self._start_time = time.time()
        self._end_time = 0.0

        self._current_job_id = None
        self._current_job_label = None

        self._job_statuses.clear()
        self._job_labels.clear()
        self._job_durations.clear()
        self._job_errors.clear()
        self._timeline_events.clear()
        self._log_entries.clear()

        self.execution_started.emit(total_jobs)
        self._emit_progress()

    def finalize(self) -> None:
        """Mark execution as complete and emit final signals."""
        logger.info(
            "[session] finalize: completed=%d  failed=%d  cached=%d  duration=%.2fs",
            self._completed_jobs, self._failed_jobs, self._cached_jobs,
            self.elapsed_duration,
        )
        self._is_running = False
        self._end_time = time.time()
        self._running_jobs = 0
        self._current_job_id = None
        self._current_job_label = None

        self._emit_progress()
        self._emit_stats()
        self.execution_completed.emit()

    def abort(self) -> None:
        """Mark execution as aborted."""
        logger.warning("[session] abort")
        self._is_running = False
        self._was_aborted = True
        self._end_time = time.time()
        self._running_jobs = 0
        self._current_job_id = None
        self._current_job_label = None

        # Mark any still-running jobs as ABORTED
        for jid, st in list(self._job_statuses.items()):
            if st == "RUNNING":
                self._job_statuses[jid] = "ABORTED"
                self._timeline_events.append({
                    "job_id": jid, "status": "ABORTED", "timestamp": time.time(),
                })
                self.timeline_event.emit(jid, "ABORTED")
                self.job_aborted.emit(jid)

        self._emit_progress()
        self._emit_stats()
        self.execution_aborted.emit()

    def sync_from_batch_jobs(self, jobs: list) -> None:
        """
        Re-synchronise execution session state from a list of BatchJob objects.
        Rebuilds counters, timeline events, statuses, and log entries from actual batch queue jobs.
        """
        self._total_jobs = len(jobs)
        self._running_jobs = sum(1 for j in jobs if getattr(j, "status", "") == "RUNNING")
        self._completed_jobs = sum(1 for j in jobs if getattr(j, "status", "") in ("COMPLETED", "CACHED"))
        self._failed_jobs = sum(1 for j in jobs if getattr(j, "status", "") == "FAILED")
        self._cached_jobs = sum(1 for j in jobs if getattr(j, "status", "") == "CACHED")

        self._job_statuses.clear()
        self._job_labels.clear()
        self._job_durations.clear()
        self._job_errors.clear()
        self._timeline_events.clear()

        # Track existing logged node IDs to prevent duplicate log creation
        logged_job_ids = set()
        for entry_str in self._log_entries:
            try:
                entry = json.loads(entry_str)
                nid = entry.get("node_id")
                if nid:
                    logged_job_ids.add(nid)
            except Exception:
                pass

        from datetime import datetime, timezone

        for j in jobs:
            jid = getattr(j, "job_id", "")
            st = getattr(j, "status", "PENDING")
            lbl = getattr(j, "label", jid)
            dur = getattr(j, "duration", None)
            err = getattr(j, "error", None)
            tb = getattr(j, "traceback", None)

            self._job_statuses[jid] = st
            self._job_labels[jid] = lbl
            if dur is not None:
                self._job_durations[jid] = dur
            if err:
                self._job_errors[jid] = err

            self._timeline_events.append({
                "job_id": jid,
                "status": st,
                "timestamp": time.time(),
            })

            # Create synthetic log entry if no log exists for this job ID yet
            if jid and jid not in logged_job_ids:
                level = "ERROR" if st == "FAILED" else ("WARNING" if st == "ABORTED" else "INFO")
                dur_str = f" ({dur:.2f}s)" if dur is not None else ""
                log_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": level,
                    "node_id": jid,
                    "status": st,
                    "duration_ms": (dur * 1000.0) if dur is not None else None,
                    "message": f"Batch job '{lbl}' ({jid}) status: {st}{dur_str}",
                }
                if err:
                    log_data["error"] = err
                if tb:
                    log_data["traceback"] = tb

                self._log_entries.append(json.dumps(log_data))

        self._emit_progress()
        self._emit_stats()

    # ------------------------------------------------------------------
    # Job updates
    # ------------------------------------------------------------------

    def update_job(
        self,
        job_id: str,
        status: str,
        label: Optional[str] = None,
        duration: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Update the status of a single job and emit appropriate signals.

        Called by ``BatchController._on_job_updated`` for every status
        transition.
        """
        prev_status = self._job_statuses.get(job_id)
        self._job_statuses[job_id] = status

        if label:
            self._job_labels[job_id] = label

        # Track counters
        if prev_status == "RUNNING":
            self._running_jobs = max(0, self._running_jobs - 1)

        if status == "RUNNING":
            self._running_jobs += 1
            self._current_job_id = job_id
            self._current_job_label = label or self._job_labels.get(job_id, job_id)
            self.job_started.emit(job_id, self._current_job_label)

        elif status == "COMPLETED":
            self._completed_jobs += 1
            dur = duration or 0.0
            self._job_durations[job_id] = dur
            self.job_completed.emit(job_id, dur)

        elif status == "FAILED":
            self._failed_jobs += 1
            if error:
                self._job_errors[job_id] = error
            self.job_failed.emit(job_id, error or "Unknown error")

        elif status == "ABORTED":
            self.job_aborted.emit(job_id)

        elif status == "CACHED":
            self._cached_jobs += 1
            self._completed_jobs += 1
            if duration:
                self._job_durations[job_id] = duration
            self.job_cached.emit(job_id)

        # Timeline
        self._timeline_events.append({
            "job_id": job_id, "status": status, "timestamp": time.time(),
        })
        self.timeline_event.emit(job_id, status)

        self._emit_progress()

    # ------------------------------------------------------------------
    # Log forwarding
    # ------------------------------------------------------------------

    def add_log(self, json_str: str) -> None:
        """Append a log entry and emit signal for live display."""
        self._log_entries.append(json_str)
        self.log_entry.emit(json_str)

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """Explicitly clear all stored execution data."""
        self._is_running = False
        self._was_aborted = False
        self._total_jobs = 0
        self._running_jobs = 0
        self._completed_jobs = 0
        self._failed_jobs = 0
        self._cached_jobs = 0
        self._start_time = 0.0
        self._end_time = 0.0

        self._current_job_id = None
        self._current_job_label = None

        self._job_statuses.clear()
        self._job_labels.clear()
        self._job_durations.clear()
        self._job_errors.clear()
        self._timeline_events.clear()
        self._log_entries.clear()

    # ------------------------------------------------------------------
    # Serialisation (for SessionManager persistence)
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise execution state for persistence."""
        return {
            "is_running": False,  # never persist as "running"
            "was_aborted": self._was_aborted,
            "total_jobs": self._total_jobs,
            "completed_jobs": self._completed_jobs,
            "failed_jobs": self._failed_jobs,
            "cached_jobs": self._cached_jobs,
            "start_time": self._start_time,
            "end_time": self._end_time if self._end_time > 0 else time.time(),
            "job_statuses": dict(self._job_statuses),
            "job_labels": dict(self._job_labels),
            "job_durations": dict(self._job_durations),
            "job_errors": dict(self._job_errors),
            "timeline_events": list(self._timeline_events),
            # Cap log entries to avoid bloating the session file
            "log_entries": self._log_entries[-500:] if self._log_entries else [],
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """
        Restore execution state from previously saved data.

        Does NOT emit execution_started — the caller should update
        the UI manually after calling this.
        """
        if not data or not isinstance(data, dict):
            return

        self._is_running = False
        self._was_aborted = data.get("was_aborted", False)
        self._total_jobs = data.get("total_jobs", 0)
        self._running_jobs = 0  # Never restore as running
        self._completed_jobs = data.get("completed_jobs", 0)
        self._failed_jobs = data.get("failed_jobs", 0)
        self._cached_jobs = data.get("cached_jobs", 0)
        self._start_time = data.get("start_time", 0.0)
        self._end_time = data.get("end_time", 0.0)

        self._current_job_id = None
        self._current_job_label = None

        self._job_statuses = data.get("job_statuses", {})
        self._job_labels = data.get("job_labels", {})
        self._job_durations = {
            k: float(v) for k, v in data.get("job_durations", {}).items()
        }
        self._job_errors = data.get("job_errors", {})
        self._timeline_events = data.get("timeline_events", [])
        self._log_entries = data.get("log_entries", [])

        logger.info(
            "[session] restored: total=%d  completed=%d  failed=%d",
            self._total_jobs, self._completed_jobs, self._failed_jobs,
        )

    # ------------------------------------------------------------------
    # Stats helpers
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return a full statistics dictionary."""
        return {
            "total": self._total_jobs,
            "running": self._running_jobs,
            "completed": self._completed_jobs,
            "failed": self._failed_jobs,
            "cached": self._cached_jobs,
            "duration": self.elapsed_duration,
            "success_rate": self.success_rate,
            "is_running": self._is_running,
            "was_aborted": self._was_aborted,
            "start_time": self._start_time,
        }

    # ------------------------------------------------------------------
    # Internal signal helpers
    # ------------------------------------------------------------------

    def _emit_progress(self) -> None:
        self.progress_updated.emit(
            self._total_jobs,
            self._running_jobs,
            self._completed_jobs,
            self._failed_jobs,
        )

    def _emit_stats(self) -> None:
        self.stats_updated.emit(self.get_stats())


class ExecutionSessionLogHandler(logging.Handler):
    """
    Standard Python logging.Handler that captures all application/terminal
    log records and forwards them to ExecutionSession for the Live Logs view.
    """

    def __init__(self, execution_session: ExecutionSession):
        super().__init__()
        self._session = execution_session

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from pyasl.pipeline.structured_logger import _JSONFormatter
            formatter = _JSONFormatter()
            json_str = formatter.format(record)
            self._session.add_log(json_str)
        except Exception:
            pass
