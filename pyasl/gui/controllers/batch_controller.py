"""
gui/controllers/batch_controller.py
-------------------------------------
Business-logic controller for the Batch Mode tab.

Owns the ``BatchState`` model and manages job CRUD, execution via
``BatchWorkerThread``, and report generation.

Integrates with ``SessionManager`` for auto-save persistence and
``CacheManager`` for skipping previously-processed jobs.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger("pyasl.gui.batch_controller")


try:
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.models.batch_state import BatchState, BatchJob


class BatchController(QObject):
    """
    Signals
    -------
    job_added(BatchJob)
    job_removed(job_ids)
    jobs_cleared()
    job_status_changed(job_id, status)
    batch_started()
    batch_completed(results_list)
    error(message)
    """

    job_added = pyqtSignal(object)           # BatchJob
    job_removed = pyqtSignal(list)            # list[str]
    jobs_cleared = pyqtSignal()
    job_status_changed = pyqtSignal(str, str)
    batch_started = pyqtSignal()
    batch_completed = pyqtSignal(list)
    report_ready = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, parent=None, session=None, cache=None, execution_session=None):
        super().__init__(parent)
        self.state = BatchState()
        self._worker = None
        self._session = session          # SessionManager (optional)
        self._cache = cache              # CacheManager (optional)
        self._execution_session = execution_session  # ExecutionSession (optional)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _auto_save_session(self) -> None:
        """Persist current batch state to the session file."""
        if self._session is None:
            return
        jobs_data = []
        for j in self.state.jobs:
            jobs_data.append({
                "job_id": j.job_id,
                "label": j.label,
                "data_dir": j.data_dir,
                "config_path": j.config_path,
                "pipeline_type": j.pipeline_type,
                "status": j.status,
                "duration": j.duration,
            })
        self._session.set_batch_jobs(jobs_data)

        # Also persist execution session state
        if self._execution_session is not None:
            self._session.set_execution_history(
                self._execution_session.to_dict()
            )

    def _snapshot_pipeline_state(self) -> None:
        """Save pipeline state from session (called after processing)."""
        self._auto_save_session()

    # ------------------------------------------------------------------
    # Restore from session
    # ------------------------------------------------------------------

    def restore_jobs(self, jobs_data: List[Dict]) -> None:
        """
        Repopulate ``BatchState`` from previously saved session data.

        Each item in *jobs_data* is a dict with keys matching the
        session.json ``batch_jobs`` schema.
        """
        for jd in jobs_data:
            job = BatchJob(
                data_dir=jd.get("data_dir", ""),
                config_path=jd.get("config_path", ""),
                pipeline_type=jd.get("pipeline_type", "legacy"),
                job_id=jd.get("job_id"),
                label=jd.get("label"),
            )
            job.status = jd.get("status", "PENDING")
            job.duration = jd.get("duration")
            self.state._jobs.append(job)
            self.job_added.emit(job)

    # ------------------------------------------------------------------
    # Job CRUD
    # ------------------------------------------------------------------

    def add_job(self, data_dir: str, config_path: str) -> BatchJob:
        # Validate data_dir
        if not data_dir or not os.path.exists(data_dir):
            raise ValueError(f"Invalid data directory: '{data_dir}' does not exist.")
        if not os.path.isdir(data_dir):
            raise ValueError(f"Invalid data directory: '{data_dir}' is not a directory.")
        if not os.listdir(data_dir):
            raise ValueError(f"Invalid data directory: '{data_dir}' is empty.")

        # Validate config_path & schema
        if not config_path or not os.path.exists(config_path):
            raise ValueError(f"Invalid config file: '{config_path}' does not exist.")
        if not os.path.isfile(config_path):
            raise ValueError(f"Invalid config file: '{config_path}' is not a file.")

        try:
            from pyasl.pipeline.config_parser import validate_yaml_config
            validate_yaml_config(config_path)
        except Exception as exc:
            raise ValueError(f"YAML Schema Validation Failed for '{config_path}': {exc}") from exc

        job = self.state.add_job(data_dir, config_path)
        self.job_added.emit(job)
        self._auto_save_session()
        logger.info("[ctrl]  Job added: id=%s  label=%s  config=%s",
                    job.job_id, job.label, os.path.basename(config_path))
        return job

    def remove_jobs(self, job_ids: List[str]) -> None:
        self.state.remove_jobs(job_ids)
        self.job_removed.emit(job_ids)
        self._auto_save_session()

    def clear(self) -> None:
        logger.info("[ctrl]  Clearing all batch jobs from queue.")
        self.state.clear()
        self.jobs_cleared.emit()
        self._auto_save_session()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, max_workers: int = 2) -> None:
        """Launch batch execution in a background thread with cache consultation."""
        if self.state.count == 0:
            logger.warning("[ctrl]  run() called with no jobs — emitting error.")
            self.error.emit("Add at least one job first.")
            return

        total_jobs = len(self.state.jobs)
        logger.info("[ctrl]  run() called: total_jobs=%d  max_workers=%d",
                    total_jobs, max_workers)

        from pyasl.batch import BatchJob as EngineBatchJob
        from pyasl.gui.threads.batch_worker import BatchWorkerThread

        uncached_batch_jobs = []
        cached_results = []

        for j in self.state.jobs:
            cached_res = self.get_cached_result(j.data_dir, j.config_path) if self._cache else None
            if cached_res:
                self.state.update_status(j.job_id, "CACHED")
                if "duration" in cached_res:
                    self.state.update_duration(j.job_id, cached_res["duration"])
                self.job_status_changed.emit(j.job_id, "CACHED")
                cached_res["status"] = "CACHED"
                cached_results.append(cached_res)
                logger.info("[ctrl]  Cache HIT for job '%s' — skipping execution.", j.job_id)
            else:
                uncached_batch_jobs.append(
                    EngineBatchJob(
                        data_dir=j.data_dir,
                        config_path=j.config_path,
                        pipeline_type=j.pipeline_type,
                        job_id=j.job_id,
                        label=j.label,
                    )
                )
                logger.info("[ctrl]  Job '%s' queued for execution: data=%s  config=%s",
                            j.job_id, os.path.basename(j.data_dir), os.path.basename(j.config_path))

        # Initialize shared execution session
        if self._execution_session is not None:
            self._execution_session.begin(total_jobs)
            # Report cached jobs to the execution session
            for cr in cached_results:
                job_id = cr.get("job_id", "")
                job = self.state.get_job(job_id)
                self._execution_session.update_job(
                    job_id, "CACHED",
                    label=job.label if job else job_id,
                    duration=cr.get("duration"),
                )

        self.batch_started.emit()

        if not uncached_batch_jobs:
            logger.info("[ctrl]  All %d job(s) served from cache — no execution needed.",
                        len(cached_results))
            self._on_batch_done(cached_results)
            return

        def _on_worker_batch_done(new_results: list) -> None:
            combined = cached_results + new_results
            self._on_batch_done(combined)

        self._worker = BatchWorkerThread(uncached_batch_jobs, max_workers=max_workers)
        self._worker.job_updated.connect(self._on_job_updated)
        self._worker.batch_done.connect(_on_worker_batch_done)
        self._worker.error_occurred.connect(self.error.emit)

        # Forward log entries from worker → execution session
        if self._execution_session is not None:
            self._worker.log_produced.connect(self._execution_session.add_log)

        self._worker.start()

    def abort(self) -> None:
        if self._worker and self._worker.isRunning():
            logger.warning("[ctrl]  abort() called — signalling BatchWorkerThread.")
            self._worker.abort()

            # Notify execution session of abort
            if self._execution_session is not None:
                self._execution_session.abort()

    # ------------------------------------------------------------------
    # Internal signal handlers
    # ------------------------------------------------------------------

    def _on_job_updated(self, job_id: str, status: str, result=None) -> None:
        self.state.update_status(job_id, status)
        if result:
            self.state.update_duration(job_id, result.duration)
            self.state.update_error(job_id, result.error, result.traceback)
        self.job_status_changed.emit(job_id, status)
        self._auto_save_session()

        # Update shared execution session
        if self._execution_session is not None:
            job = self.state.get_job(job_id)
            self._execution_session.update_job(
                job_id, status,
                label=job.label if job else None,
                duration=getattr(result, "duration", None) if result else None,
                error=getattr(result, "error", None) if result else None,
            )

        # Log every status transition
        if status == "RUNNING":
            logger.info("[ctrl]  Job '%s' -> RUNNING", job_id)
        elif status == "COMPLETED":
            dur = getattr(result, "duration", None) if result else None
            logger.info("[ctrl]  Job '%s' -> COMPLETED  duration=%s",
                        job_id, f"{dur:.3f}s" if dur else "n/a")
        elif status == "FAILED":
            err = getattr(result, "error", "") if result else ""
            logger.error("[ctrl]  Job '%s' -> FAILED  error=%s", job_id, err)
        elif status == "ABORTED":
            logger.warning("[ctrl]  Job '%s' -> ABORTED", job_id)

    def _on_batch_done(self, results: list) -> None:
        completed = sum(1 for r in results if r.get("status") in ("COMPLETED", "CACHED"))
        failed    = sum(1 for r in results if r.get("status") == "FAILED")
        logger.info("[ctrl]  Batch done: total=%d  completed=%d  failed=%d",
                    len(results), completed, failed)

        # Finalize shared execution session
        if self._execution_session is not None:
            self._execution_session.finalize()

        for res in results:
            if "status" in res:
                self.state.update_status(res["job_id"], res["status"])
            self.state.update_duration(
                res["job_id"], res.get("duration")
            )
            self.state.update_error(
                res["job_id"], res.get("error"), res.get("traceback")
            )

        # Cache completed results
        self._cache_results(results)

        # Generate Batch HTML Report
        try:
            from pyasl.batch.report import generate_report
            from pyasl.batch.job import BatchResult, BatchStatus

            batch_results = []
            for res in results:
                status_str = res.get("status", "COMPLETED")
                try:
                    b_status = BatchStatus(status_str)
                except ValueError:
                    b_status = BatchStatus.COMPLETED

                br = BatchResult(
                    job_id=res["job_id"],
                    status=b_status,
                    data_dir=res.get("data_dir", ""),
                    config_path=res.get("config_path", ""),
                    start_time=res.get("start_time", 0.0) or 0.0,
                    end_time=res.get("end_time", 0.0) or 0.0,
                    result=res.get("result"),
                    error=res.get("error"),
                    traceback=res.get("traceback"),
                )
                batch_results.append(br)

            reports_dir = os.path.expanduser("~/.pyasl_workspace/reports")
            os.makedirs(reports_dir, exist_ok=True)
            html_path, _ = generate_report(batch_results, reports_dir)
            self.latest_report_path = html_path
            logger.info("[ctrl]  HTML report generated: %s", html_path)
            self.report_ready.emit(html_path)
        except Exception as exc:
            logger.error("[ctrl]  Report generation failed: %s", exc)
            self.error.emit(f"Failed to generate report: {exc}")

        self.batch_completed.emit(results)
        self._auto_save_session()

    def _cache_results(self, results: list) -> None:
        """Store completed job results in the cache."""
        if self._cache is None:
            return
        for res in results:
            if res.get("status") == "COMPLETED":
                job = self.state.get_job(res["job_id"])
                if job:
                    self._cache.store_result(
                        job.data_dir,
                        job.config_path,
                        res,
                    )

    def get_cached_result(
        self, data_dir: str, config_path: str
    ) -> Optional[dict]:
        """Check if a result is cached for the given inputs."""
        if self._cache is None:
            return None
        return self._cache.get_cached_result(data_dir, config_path)

    # ------------------------------------------------------------------
    # Error handler exposed to outer callers
    # ------------------------------------------------------------------

    def _on_batch_error(self, msg: str) -> None:
        """Called when error signal is emitted by the worker."""
        logger.error("[ctrl]  Batch error received: %s", msg)
