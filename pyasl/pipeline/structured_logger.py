"""
structured_logger.py
---------------------
JSON-lines structured logger for the PyASL pipeline framework.

Features
--------
- Emits one JSON object per line to a rotating log file
- Also pushes entries to an in-process queue for GUI consumption
- Thread-safe queue suitable for QTimer polling from PyQt6 GUI
- Singleton logger accessed via module-level helpers

Usage
-----
    from pyasl.pipeline.structured_logger import get_logger, set_log_file

    log = get_logger()
    log.node_started("my_node")
    log.node_finished("my_node", status="COMPLETED", duration_ms=120.5)
    log.pipeline_event("asl_pipeline", status="completed", duration_ms=350.0)
    log.info("Any free-text message", pipeline="asl_pipeline")

    # In GUI: drain the queue
    while not log.queue.empty():
        entry = log.queue.get_nowait()
        display(entry)
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

_LOG_FILE_DEFAULT = os.path.join(os.path.expanduser("~"), ".pyasl_pipeline.jsonl")


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class _JSONFormatter(logging.Formatter):
    """Format a LogRecord as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # attach extra structured fields if present
        for key in ("pipeline", "node_id", "step", "status",
                    "duration_ms", "error", "function", "inputs",
                    "outputs", "params", "step_index", "total_steps", "traceback"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


# ---------------------------------------------------------------------------
# Queue handler — pushes entries to an in-process queue for GUI
# ---------------------------------------------------------------------------

class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self._q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = json.loads(self.format(record))
            self._q.put_nowait(entry)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# StructuredLogger
# ---------------------------------------------------------------------------

class StructuredLogger:
    """
    Thin wrapper around Python's logging that adds:
    - structured keyword arguments mapped to JSON fields
    - an in-process queue for GUI consumption
    - convenience methods for pipeline events
    """

    def __init__(self, name: str = "pyasl.pipeline") -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        self.queue: queue.Queue = queue.Queue(maxsize=10_000)
        self._lock = threading.Lock()
        self._file_handler: Optional[RotatingFileHandler] = None

        # Always attach queue handler
        q_handler = _QueueHandler(self.queue)
        q_handler.setFormatter(_JSONFormatter())
        self._logger.addHandler(q_handler)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_log_file(self, path: str, max_bytes: int = 10 * 1024 * 1024,
                     backup_count: int = 3) -> None:
        """Attach a rotating file handler writing JSON-lines."""
        with self._lock:
            if self._file_handler:
                self._logger.removeHandler(self._file_handler)
                self._file_handler.close()
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            fh = RotatingFileHandler(path, maxBytes=max_bytes,
                                     backupCount=backup_count, encoding="utf-8")
            fh.setFormatter(_JSONFormatter())
            self._logger.addHandler(fh)
            self._file_handler = fh

    def add_stream_handler(self, level: int = logging.INFO) -> None:
        """Also print human-readable lines to stdout."""
        import sys
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(level)
        sh.setFormatter(logging.Formatter(
            "[%(levelname)s] %(asctime)s  %(message)s",
            datefmt="%H:%M:%S",
        ))
        self._logger.addHandler(sh)

    # ------------------------------------------------------------------
    # Internal emit helper
    # ------------------------------------------------------------------

    def _emit(self, level: int, msg: str, **extra: Any) -> None:
        record = self._logger.makeRecord(
            self._logger.name, level, "(pipeline)", 0,
            msg, (), None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        self._logger.handle(record)

    # ------------------------------------------------------------------
    # Convenience API
    # ------------------------------------------------------------------

    def debug(self, msg: str, **kw: Any) -> None:
        self._emit(logging.DEBUG, msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._emit(logging.INFO, msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._emit(logging.WARNING, msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._emit(logging.ERROR, msg, **kw)

    # ------------------------------------------------------------------
    # Pipeline-specific events
    # ------------------------------------------------------------------

    def node_started(self, node_id: str, pipeline: str = "",
                     function: str = "", **kw: Any) -> None:
        self._emit(
            logging.INFO,
            f"Node started: {node_id}",
            node_id=node_id,
            pipeline=pipeline,
            function=function,
            status="RUNNING",
            step="node_start",
            **kw,
        )

    def node_finished(self, node_id: str, status: str = "COMPLETED",
                      duration_ms: float = 0.0, pipeline: str = "",
                      error: Optional[str] = None, **kw: Any) -> None:
        level = logging.INFO if status == "COMPLETED" else logging.ERROR
        extra: Dict[str, Any] = dict(
            node_id=node_id, pipeline=pipeline,
            status=status, duration_ms=round(duration_ms, 2),
            step="node_finish",
            **kw,
        )
        if error:
            extra["error"] = error
        self._emit(level, f"Node {status.lower()}: {node_id}", **extra)

    def pipeline_event(self, pipeline: str, status: str,
                       duration_ms: float = 0.0, **kw: Any) -> None:
        level = logging.INFO if status in ("completed", "started") else logging.ERROR
        self._emit(
            level,
            f"Pipeline {status}: {pipeline}",
            pipeline=pipeline,
            status=status,
            duration_ms=round(duration_ms, 2),
            step="pipeline_event",
            **kw,
        )

    def drain(self) -> list:
        """Return all queued entries (non-blocking)."""
        entries = []
        try:
            while True:
                entries.append(self.queue.get_nowait())
        except queue.Empty:
            pass
        return entries


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_default_logger: Optional[StructuredLogger] = None
_default_lock = threading.Lock()


def get_logger() -> StructuredLogger:
    """Return the global StructuredLogger singleton."""
    global _default_logger
    with _default_lock:
        if _default_logger is None:
            _default_logger = StructuredLogger()
    return _default_logger


def set_log_file(path: str) -> None:
    """Configure the global logger to write to `path`."""
    get_logger().set_log_file(path)
