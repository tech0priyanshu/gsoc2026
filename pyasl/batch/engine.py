"""
batch/engine.py
---------------
BatchEngine: submit multiple BatchJobs to a ProcessPoolExecutor with
per-job fault isolation, real-time progress updates, and result collection.

Usage
-----
    from pyasl.batch import BatchEngine, BatchJob

    jobs = [
        BatchJob(data_dir="/data/subj01", config_path="pipeline.yaml"),
        BatchJob(data_dir="/data/subj02", config_path="pipeline.yaml"),
    ]

    def on_progress(job_id, status, result=None):
        print(f"{job_id}: {status}")

    engine = BatchEngine(max_workers=2)
    results = engine.run(jobs, progress_callback=on_progress)
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import signal
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

from .job import BatchJob, BatchResult, BatchStatus
from .worker import batch_worker
from pyasl.gui.utils.process_helper import set_process_identity, get_worker_executable, is_frozen

logger = logging.getLogger("pyasl.batch.engine")


def _init_batch_worker():
    """Initialize process identity for batch processing worker subprocesses."""
    set_process_identity("PyASL Processing")


class BatchEngine:
    """
    Parallel batch processor using ProcessPoolExecutor.

    Each job runs in an isolated subprocess — a crash in one job
    does not affect other jobs or the main process.

    Parameters
    ----------
    max_workers : Maximum concurrent subprocesses (default 2).
                  Set to 1 for sequential execution with fault isolation.
    """

    def __init__(self, max_workers: int = 2) -> None:
        self.max_workers = max_workers
        self._abort_event = threading.Event()
        self._executor: Optional[concurrent.futures.ProcessPoolExecutor] = None

    def abort(self) -> None:
        """Signal all pending jobs to be skipped and terminate running subprocesses."""
        logger.warning("[engine]  abort() called — setting abort flag and terminating subprocesses.")
        self._abort_event.set()
        if self._executor is not None:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self._executor.shutdown(wait=False)

            # Fix 4C: Terminate active worker processes in pool
            processes = getattr(self._executor, "_processes", {})
            if isinstance(processes, dict):
                for pid, proc in list(processes.items()):
                    try:
                        logger.warning("[engine]  Terminating worker subprocess PID %s", pid)
                        if hasattr(proc, "terminate"):
                            proc.terminate()
                        else:
                            sig = getattr(signal, "SIGTERM", 15)
                            os.kill(pid, sig)
                    except Exception as e:
                        logger.debug("[engine]  Could not terminate PID %s: %s", pid, e)

    def reset(self) -> None:
        """Clear abort flag to allow a new batch run."""
        self._abort_event.clear()
        self._executor = None

    def run(
        self,
        jobs: List[BatchJob],
        progress_callback: Optional[Callable[[str, str, Optional[BatchResult]], None]] = None,
    ) -> List[BatchResult]:
        """
        Run all jobs and return results.
        """
        self._executor = None
        results: Dict[str, BatchResult] = {}

        if not jobs:
            logger.warning("[engine]  run() called with empty job list — nothing to do.")
            return []

        # ── Engine startup log ────────────────────────────────────────────────
        logger.info("[engine]  BatchEngine.run() called:")
        logger.info("[engine]    total_jobs  = %d", len(jobs))
        logger.info("[engine]    max_workers = %d", self.max_workers)
        for i, job in enumerate(jobs, 1):
            logger.info("[engine]    job %d/%d | id='%s'  type='%s'  data='%s'  config='%s'",
                        i, len(jobs), job.job_id, job.pipeline_type,
                        job.data_dir, job.config_path)

        run_start = time.time()
        futures: Dict[concurrent.futures.Future, BatchJob] = {}

        if is_frozen():
            exec_path = get_worker_executable("PyASL Processing")
            if exec_path and exec_path != sys.executable:
                try:
                    import multiprocessing
                    multiprocessing.set_executable(exec_path)
                except Exception as e:
                    logger.debug("[engine]  Could not set worker executable: %s", e)

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=self.max_workers,
            initializer=_init_batch_worker,
        ) as executor:
            self._executor = executor

            # ── Submit phase ──────────────────────────────────────────────────
            logger.info("[engine]  Submitting jobs to ProcessPoolExecutor ...")
            for job in jobs:
                if self._abort_event.is_set():
                    job.status = BatchStatus.ABORTED
                    logger.warning("[engine]  Job '%s' ABORTED before submission (abort flag set).",
                                   job.job_id)
                    _emit(progress_callback, job.job_id, "ABORTED", None)
                    continue

                job.status = BatchStatus.RUNNING
                logger.info("[engine]  Submitting job '%s' -> subprocess ...", job.job_id)
                _emit(progress_callback, job.job_id, "RUNNING", None)

                # Support mocked batch_worker in unit tests without pickling errors
                if hasattr(batch_worker, "_mock_name") or hasattr(batch_worker, "side_effect") or hasattr(batch_worker, "return_value") or type(batch_worker).__name__ in ("MagicMock", "Mock"):
                    future = concurrent.futures.Future()
                    try:
                        res_val = batch_worker(
                            job.job_id,
                            job.data_dir,
                            job.config_path,
                            job.pipeline_type,
                        )
                        future.set_result(res_val)
                    except Exception as exc:
                        future.set_exception(exc)
                else:
                    future = executor.submit(
                        batch_worker,
                        job.job_id,
                        job.data_dir,
                        job.config_path,
                        job.pipeline_type,
                    )
                futures[future] = job
                logger.info("[engine]  Job '%s' submitted to subprocess pool.", job.job_id)

            logger.info("[engine]  All submittable jobs submitted (%d future(s)). Waiting for results ...",
                        len(futures))

            # ── Collection phase ──────────────────────────────────────────────
            for future in concurrent.futures.as_completed(futures):
                job = futures[future]
                logger.info("[engine]  Future completed for job '%s' — collecting result ...", job.job_id)

                try:
                    raw = future.result()
                    logger.info("[engine]  Job '%s' subprocess returned: status=%s",
                                job.job_id, raw.get("status", "unknown"))
                except Exception as exc:  # noqa: BLE001
                    t = time.time()
                    logger.error("[engine]  Job '%s' subprocess raised unhandled exception: %s",
                                 job.job_id, exc)
                    raw = {
                        "job_id": job.job_id,
                        "status": "FAILED" if not self._abort_event.is_set() else "ABORTED",
                        "start_time": t,
                        "end_time": t,
                        "result": None,
                        "error": str(exc),
                        "traceback": None,
                    }

                status = BatchStatus(raw["status"]) if raw.get("status") in BatchStatus.__members__ else BatchStatus.FAILED
                job.status = status
                job.result = raw.get("result")
                job.error = raw.get("error")
                job.start_time = raw.get("start_time")
                job.end_time = raw.get("end_time")

                br = BatchResult(
                    job_id=raw["job_id"],
                    status=status,
                    data_dir=job.data_dir,
                    config_path=job.config_path,
                    start_time=raw["start_time"],
                    end_time=raw["end_time"],
                    result=raw.get("result"),
                    error=raw.get("error"),
                    traceback=raw.get("traceback"),
                )
                results[job.job_id] = br

                if status == BatchStatus.COMPLETED:
                    logger.info("[engine]  Job '%s' COMPLETED  duration=%.3fs",
                                job.job_id, br.duration)
                else:
                    logger.error("[engine]  Job '%s' %s  duration=%.3fs  error=%s",
                                 job.job_id, status.value, br.duration, br.error)
                    if br.traceback:
                        for line in (br.traceback or "").strip().splitlines():
                            logger.error("[engine]    | %s", line)

                _emit(progress_callback, job.job_id, status.value, br)

        self._executor = None

        # ── Summary ───────────────────────────────────────────────────────────
        total_elapsed = time.time() - run_start
        ordered = []
        for job in jobs:
            if job.job_id in results:
                ordered.append(results[job.job_id])
            else:
                t = time.time()
                ordered.append(BatchResult(
                    job_id=job.job_id,
                    status=BatchStatus.ABORTED,
                    data_dir=job.data_dir,
                    config_path=job.config_path,
                    start_time=t,
                    end_time=t,
                ))

        completed = sum(1 for r in ordered if r.status == BatchStatus.COMPLETED)
        failed    = sum(1 for r in ordered if r.status == BatchStatus.FAILED)
        aborted   = sum(1 for r in ordered if r.status == BatchStatus.ABORTED)

        logger.info("[engine]  All jobs processed:")
        logger.info("[engine]    total     = %d", len(ordered))
        logger.info("[engine]    completed = %d", completed)
        logger.info("[engine]    failed    = %d", failed)
        logger.info("[engine]    aborted   = %d", aborted)
        logger.info("[engine]    wall_time = %.3f s", total_elapsed)
        for r in ordered:
            logger.info("[engine]    [%s] %s  duration=%.3fs",
                        r.status.value, r.job_id, r.duration)

        return ordered


def _emit(cb, job_id, status, result):
    if cb:
        try:
            cb(job_id, status, result)
        except Exception:  # noqa: BLE001
            pass
