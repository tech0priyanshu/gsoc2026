"""
gui/threads/pipeline_worker.py
-------------------------------
QThread worker for non-blocking single-pipeline execution.
Executes the pipeline in an isolated background process ('PyASL Worker')
and emits Qt signals so the GUI can update safely from the main thread.
Falls back to thread-based execution if the pipeline payload contains
unpicklable objects (e.g. in-memory test closures).
"""
from __future__ import annotations

import json
import logging
import multiprocessing
import queue
import sys
from typing import Optional

try:
    from PyQt6.QtCore import QThread, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError(
        "PyQt6 is required for the GUI. Install with: pip install PyQt6"
    )

from pyasl.pipeline.exceptions.errors import PipelineAbortedError
from pyasl.pipeline.structured_logger import get_logger
from pyasl.gui.utils.process_helper import set_process_identity, get_worker_executable, is_frozen

logger = logging.getLogger("pyasl.gui.pipeline_worker")


def _extract_pipeline_error(result: dict) -> str:
    err_msg = result.get("error")
    if not err_msg and "nodes" in result:
        for node_data in result.get("nodes", {}).values():
            if isinstance(node_data, dict) and node_data.get("error"):
                err_msg = node_data["error"]
                break
    return err_msg or "Pipeline execution failed."


def _single_pipeline_process_target(pipeline, event_queue: multiprocessing.Queue) -> None:
    """
    Subprocess target function for executing a single pipeline in an isolated process.

    Parameters
    ----------
    pipeline : Pipeline object to execute
    event_queue : multiprocessing.Queue to send execution progress and results
    """
    set_process_identity("PyASL Worker")
    log = get_logger()

    def _drain():
        for entry in log.drain():
            try:
                event_queue.put(("log", json.dumps(entry)))
            except Exception:
                pass

    def _progress_cb(node_id: str, status: str) -> None:
        _drain()
        try:
            event_queue.put(("progress", (node_id, status)))
        except Exception:
            pass

    pipeline.progress_callback = _progress_cb

    try:
        result = pipeline.execute()
        _drain()
        if isinstance(result, dict) and result.get("status") == "failed":
            event_queue.put(("error", _extract_pipeline_error(result)))
        else:
            event_queue.put(("done", result))
    except PipelineAbortedError:
        _drain()
        event_queue.put(("done", {
            "pipeline": getattr(pipeline, "name", "pipeline"),
            "status": "aborted",
            "nodes": {},
            "execution_log": getattr(pipeline, "execution_log", []),
        }))
    except Exception as exc:  # noqa: BLE001
        _drain()
        event_queue.put(("error", str(exc)))


class PipelineWorkerThread(QThread):
    """
    Runs a Pipeline in an isolated background worker process ('PyASL Worker').

    Signals
    -------
    node_started(node_id)
    node_finished(node_id, status)   status: 'COMPLETED' | 'FAILED'
    pipeline_done(result_dict)
    log_line(json_str)               one JSON log entry per signal
    error_occurred(message)
    """

    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str, str)
    pipeline_done = pyqtSignal(dict)
    log_line = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._process: Optional[multiprocessing.Process] = None
        self._event_queue: Optional[multiprocessing.Queue] = None

    def stop(self) -> None:
        """Signal the background pipeline to abort execution and terminate process."""
        if self._pipeline:
            try:
                self._pipeline.abort()
            except Exception:
                pass

        if self._process and self._process.is_alive():
            try:
                logger.warning("[worker]  Terminating single pipeline worker process PID %s", self._process.pid)
                self._process.terminate()
            except Exception as e:
                logger.debug("[worker]  Could not terminate worker process: %s", e)

    def run(self):
        ctx = multiprocessing.get_context()
        self._event_queue = ctx.Queue()

        if is_frozen():
            exec_path = get_worker_executable("PyASL Worker")
            if exec_path and exec_path != sys.executable:
                try:
                    multiprocessing.set_executable(exec_path)
                except Exception as e:
                    logger.debug("[worker]  Could not set worker executable: %s", e)

        try:
            self._process = ctx.Process(
                target=_single_pipeline_process_target,
                args=(self._pipeline, self._event_queue),
                name="PyASL Worker",
            )
            logger.info("[worker]  Starting single pipeline process ('PyASL Worker') ...")
            self._process.start()
        except (AttributeError, TypeError, Exception) as exc:
            logger.warning("[worker]  Process spawn failed (%s); falling back to thread execution.", exc)
            self._run_in_thread()
            return

        done_received = False

        while self._process.is_alive() or not self._event_queue.empty():
            try:
                event_type, data = self._event_queue.get(timeout=0.05)
                if event_type == "log":
                    self.log_line.emit(data)
                elif event_type == "progress":
                    node_id, status = data
                    if status == "RUNNING":
                        self.node_started.emit(node_id)
                    else:
                        self.node_finished.emit(node_id, status)
                elif event_type == "done":
                    done_received = True
                    self.pipeline_done.emit(data)
                elif event_type == "error":
                    done_received = True
                    self.error_occurred.emit(data)
            except queue.Empty:
                pass
            except Exception as exc:
                logger.debug("[worker]  Error reading from event queue: %s", exc)

        self._process.join(timeout=2.0)

        if not done_received and self._process.exitcode not in (0, None):
            err_msg = f"Pipeline worker process terminated unexpectedly (Exit code: {self._process.exitcode})"
            logger.error("[worker]  %s", err_msg)
            self.error_occurred.emit(err_msg)

        try:
            if hasattr(self._event_queue, "cancel_join_thread"):
                self._event_queue.cancel_join_thread()
            self._event_queue.close()
        except Exception:
            pass

    def _run_in_thread(self):
        """Fallback in-thread execution when pipeline payload cannot be pickled across processes."""
        log = get_logger()

        def _drain():
            for entry in log.drain():
                self.log_line.emit(json.dumps(entry))

        def _progress_cb(node_id: str, status: str) -> None:
            _drain()
            if status == "RUNNING":
                self.node_started.emit(node_id)
            else:
                self.node_finished.emit(node_id, status)

        self._pipeline.progress_callback = _progress_cb

        try:
            result = self._pipeline.execute()
            _drain()
            if isinstance(result, dict) and result.get("status") == "failed":
                self.error_occurred.emit(_extract_pipeline_error(result))
            else:
                self.pipeline_done.emit(result)
        except PipelineAbortedError:
            _drain()
            self.pipeline_done.emit({
                "pipeline": getattr(self._pipeline, "name", "pipeline"),
                "status": "aborted",
                "nodes": {},
                "execution_log": getattr(self._pipeline, "execution_log", []),
            })
        except Exception as exc:  # noqa: BLE001
            _drain()
            self.error_occurred.emit(str(exc))
