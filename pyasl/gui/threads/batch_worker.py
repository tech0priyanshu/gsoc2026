"""
gui/threads/batch_worker.py
----------------------------
QThread worker for non-blocking batch execution.
Emits Qt signals so the GUI can update safely from the main thread.
Every step is logged via Python logging for developer visibility.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import QThread, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError(
        "PyQt6 is required for the GUI. Install with: pip install PyQt6"
    )

logger = logging.getLogger("pyasl.gui.batch_worker_thread")


class BatchWorkerThread(QThread):
    """
    Runs a BatchEngine in a background thread.

    Signals
    -------
    job_updated(job_id, status, result)
    batch_done(results_as_list_of_dicts)
    error_occurred(message)
    """

    job_updated    = pyqtSignal(str, str, object)
    batch_done     = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    log_produced   = pyqtSignal(str)          # JSON log string

    def __init__(self, jobs: list, max_workers: int = 2, parent=None):
        super().__init__(parent)
        from pyasl.batch import BatchEngine
        self._jobs = jobs
        self._max_workers = max_workers
        self._engine = BatchEngine(max_workers=self._max_workers)

        logger.info("[thread]  BatchWorkerThread created: jobs=%d  max_workers=%d",
                    len(jobs), max_workers)

    def run(self):
        logger.info("[thread]  Background thread started.")
        logger.info("[thread]  Submitting %d job(s) to BatchEngine ...", len(self._jobs))

        def _progress_cb(job_id: str, status: str, result) -> None:
            # Emit Qt signal for GUI update (thread-safe)
            self.job_updated.emit(job_id, status, result)

            # Log every status change
            if status == "RUNNING":
                logger.info("[thread]  Job '%s' -> RUNNING", job_id)
            elif status == "COMPLETED":
                dur = getattr(result, "duration", None)
                logger.info("[thread]  Job '%s' -> COMPLETED  duration=%s",
                            job_id, f"{dur:.3f}s" if dur else "n/a")
            elif status == "FAILED":
                err = getattr(result, "error", "") if result else ""
                logger.error("[thread]  Job '%s' -> FAILED  error=%s", job_id, err)
                tb = getattr(result, "traceback", "") if result else ""
                if tb:
                    for line in tb.strip().splitlines():
                        logger.error("[thread]    | %s", line)
            elif status == "ABORTED":
                logger.warning("[thread]  Job '%s' -> ABORTED", job_id)

            # Also push to StructuredLogger queue (feeds GUI Live Logs panel)
            try:
                from pyasl.pipeline.structured_logger import get_logger
                slog = get_logger()
                lbl = getattr(result, "label", job_id) if result else job_id
                dur = getattr(result, "duration", None) if result else None
                dur_ms = dur * 1000.0 if dur is not None else 0.0

                if status == "RUNNING":
                    slog.info(f"Batch job '{lbl}' ({job_id}) started.",
                              node_id=job_id, status="RUNNING")
                elif status == "COMPLETED":
                    dur_str = f" ({dur:.2f}s)" if dur else ""
                    slog.info(f"Batch job '{lbl}' ({job_id}) completed{dur_str}.",
                              node_id=job_id, status="COMPLETED", duration_ms=dur_ms)
                elif status == "FAILED" and result:
                    err = getattr(result, "error", "Unknown error")
                    tb = getattr(result, "traceback", None)
                    slog.error(f"Batch job '{lbl}' ({job_id}) failed: {err}",
                               node_id=job_id, status="FAILED", duration_ms=dur_ms,
                               error=err, traceback=tb)
            except Exception:
                pass  # Never let logging crash the worker

            # Forward log entry to ExecutionSession via signal
            try:
                import json
                from datetime import datetime, timezone
                lbl = getattr(result, "label", job_id) if result else job_id
                dur = getattr(result, "duration", None) if result else None
                log_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "ERROR" if status == "FAILED" else ("WARNING" if status == "ABORTED" else "INFO"),
                    "node_id": job_id,
                    "status": status,
                    "duration_ms": (dur * 1000.0) if dur is not None else None,
                    "message": "",
                }
                if status == "RUNNING":
                    log_data["message"] = f"Batch job '{lbl}' ({job_id}) started."
                elif status == "COMPLETED":
                    dur_str = f" ({dur:.2f}s)" if dur is not None else ""
                    log_data["message"] = f"Batch job '{lbl}' ({job_id}) completed{dur_str}."
                elif status == "FAILED" and result:
                    log_data["message"] = f"Batch job '{lbl}' ({job_id}) failed: {getattr(result, 'error', 'Error')}"
                    log_data["error"] = getattr(result, "error", "")
                    log_data["traceback"] = getattr(result, "traceback", "")
                elif status == "ABORTED":
                    log_data["message"] = f"Batch job '{lbl}' ({job_id}) aborted."
                else:
                    log_data["message"] = f"Batch job '{lbl}' ({job_id}): {status}"
                self.log_produced.emit(json.dumps(log_data))
            except Exception:
                pass  # Never let logging crash the worker

        try:
            logger.info("[thread]  Calling BatchEngine.run() ...")
            results = self._engine.run(self._jobs, progress_callback=_progress_cb)
            logger.info("[thread]  BatchEngine.run() returned %d result(s).", len(results))

            result_dicts = [r.to_dict() for r in results]
            self.batch_done.emit(result_dicts)
            logger.info("[thread]  batch_done signal emitted.")

        except Exception as exc:  # noqa: BLE001
            logger.exception("[thread]  Unhandled exception in BatchWorkerThread.run(): %s", exc)
            self.error_occurred.emit(str(exc))

    def abort(self) -> None:
        logger.warning("[thread]  abort() called — forwarding to BatchEngine.")
        if self._engine:
            self._engine.abort()
