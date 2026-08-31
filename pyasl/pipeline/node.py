from __future__ import annotations

import logging
import random
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable, Dict, List, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum

from .exceptions.errors import NodeTimeoutError, NodeAbortedError

logger = logging.getLogger("pyasl.pipeline.node")


class NodeStatus(str, Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    RETRYING  = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    SKIPPED   = "SKIPPED"


class Node(BaseModel):
    node_id: str
    function_name: str
    depends_on: List[str] = Field(default_factory=list)
    inputs: Dict[str, str] = Field(default_factory=dict)
    outputs: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: NodeStatus = NodeStatus.PENDING

    # Resiliency and timeout settings
    max_retries: int = Field(
        default=3,
        description=(
            "Number of *retries* after the first attempt fails. "
            "Total attempts = 1 + max_retries.  E.g. max_retries=3 → 4 total attempts."
        ),
    )
    retry_delay_seconds: float = 1.0
    timeout_seconds: Optional[float] = None
    retry_history: List[Dict[str, Any]] = Field(default_factory=list)

    # runtime-only
    function: Optional[Callable] = None
    result: Optional[Dict[str, Any]] = None

    # Abort event — set externally to cancel retries / sleep
    _abort_event: Optional[threading.Event] = None

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"
        # Allow private attributes with underscore prefix
        underscore_attrs_are_private = True

    def set_abort_event(self, event: threading.Event) -> None:
        """Attach an external abort event for cancellable retries."""
        self._abort_event = event

    def validate_node(self) -> None:
        if not self.node_id:
            raise ValueError("node_id is required")
        if '.' in self.node_id:
            raise ValueError(f"Node ID '{self.node_id}' cannot contain '.'")
        if not self.function_name and not self.function:
            raise ValueError("function_name or function must be provided")

    def execute(self, resolved_inputs: Dict[str, Any]) -> Dict[str, Any]:
        self.status = NodeStatus.RUNNING
        self.retry_history.clear()
        start = time.monotonic()

        # ── Pre-flight check ─────────────────────────────────────────────────
        if not self.function:
            logger.error("  [node]  '%s' | Function not bound — cannot execute.", self.node_id)
            self.status = NodeStatus.FAILED
            self.result = {"status": "failed", "error": f"Function not bound for node {self.node_id}"}
            return self.result

        # Fix 3D: total_attempts = 1 (initial) + max_retries
        attempts = 1 + max(0, self.max_retries)
        payload = {"inputs": resolved_inputs, "config": self.config, "metadata": self.metadata}

        logger.info("  [node]  '%s' | Calling function '%s'", self.node_id, self.function_name)
        logger.info("  [node]  '%s' |   max_retries    = %d  (total_attempts = %d)",
                    self.node_id, self.max_retries, attempts)
        logger.info("  [node]  '%s' |   timeout        = %s s",
                    self.node_id, self.timeout_seconds if self.timeout_seconds else "none")
        logger.info("  [node]  '%s' |   input_keys     = %s",
                    self.node_id, list(resolved_inputs.keys()) or "(none)")
        logger.info("  [node]  '%s' |   config_keys    = %s",
                    self.node_id, list(self.config.keys()) or "(none)")

        # ── Attempt loop ─────────────────────────────────────────────────────
        for attempt in range(1, attempts + 1):

            if attempt > 1:
                # Fix 3F: Cancellable retry sleep using abort event
                self.status = NodeStatus.RETRYING
                backoff = self.retry_delay_seconds * (2 ** (attempt - 2)) + random.uniform(0.05, 0.25)
                logger.warning("  [node]  '%s' | Retry %d/%d — waiting %.2f s before next attempt ...",
                               self.node_id, attempt, attempts, backoff)

                if self._abort_event is not None:
                    # Cancellable sleep — returns True if event was set
                    aborted = self._abort_event.wait(timeout=backoff)
                    if aborted:
                        logger.warning("  [node]  '%s' | Abort event set during retry wait — aborting.",
                                       self.node_id)
                        self.status = NodeStatus.FAILED
                        self.result = {"status": "failed", "error": "Node aborted during retry wait"}
                        raise NodeAbortedError(
                            f"Node '{self.node_id}' aborted during retry wait"
                        )
                else:
                    time.sleep(backoff)

                self.status = NodeStatus.RUNNING
                logger.info("  [node]  '%s' | Retrying now (attempt %d/%d) ...",
                            self.node_id, attempt, attempts)

            if self._abort_event is not None and self._abort_event.is_set():
                logger.warning("  [node]  '%s' | Abort event set before execution — aborting.",
                               self.node_id)
                self.status = NodeStatus.FAILED
                self.result = {"status": "failed", "error": "Node aborted before execution"}
                raise NodeAbortedError(f"Node '{self.node_id}' aborted before execution")

            attempt_start = time.monotonic()
            logger.info("  [node]  '%s' | Attempt %d/%d — executing function ...",
                        self.node_id, attempt, attempts)

            try:
                # ── Fix 1D: Preemptive timeout enforcement ───────────────────
                if self.timeout_seconds and self.timeout_seconds > 0:
                    logger.info("  [node]  '%s' |   timeout enforcement active: %.1f s",
                                self.node_id, self.timeout_seconds)
                    tex = ThreadPoolExecutor(max_workers=1)
                    fut = tex.submit(self.function, payload)
                    try:
                        out = fut.result(timeout=self.timeout_seconds)
                    except FuturesTimeoutError:
                        # Cancel the future (won't interrupt running thread,
                        # but prevents it from being collected)
                        fut.cancel()
                        # Shut down without waiting for the hung thread
                        tex.shutdown(wait=False)
                        self.status = NodeStatus.TIMED_OUT
                        err_msg = (
                            f"Node '{self.node_id}' exceeded timeout of "
                            f"{self.timeout_seconds}s."
                        )
                        logger.error("  [node]  '%s' | TIMED OUT — %s", self.node_id, err_msg)
                        self.result = {"status": "failed", "error": err_msg, "timed_out": True}
                        raise NodeTimeoutError(err_msg)
                    finally:
                        tex.shutdown(wait=False)
                else:
                    # ── No timeout ───────────────────────────────────────────
                    out = self.function(payload)

                # ── Function returned ─────────────────────────────────────────
                end = time.monotonic()
                attempt_elapsed = end - attempt_start
                logger.info("  [node]  '%s' | Attempt %d/%d returned in %.3f s",
                            self.node_id, attempt, attempts, attempt_elapsed)

                if not isinstance(out, dict):
                    logger.info("  [node]  '%s' |   Output was not a dict (type=%s) — wrapping.",
                                self.node_id, type(out).__name__)
                    out = {"status": "success", "outputs": out}

                out.setdefault("status", "success")
                out.setdefault("outputs", {})
                out["execution_time"] = round(end - start, 4)
                self.result = out
                self.status = (
                    NodeStatus.COMPLETED if out.get("status") == "success"
                    else NodeStatus.FAILED
                )

                output_keys = list((out.get("outputs") or {}).keys())
                logger.info("  [node]  '%s' | Function call result:",  self.node_id)
                logger.info("  [node]  '%s' |   final_status   = %s", self.node_id, self.status.value)
                logger.info("  [node]  '%s' |   execution_time = %.4f s", self.node_id, out["execution_time"])
                logger.info("  [node]  '%s' |   output_keys    = %s", self.node_id, output_keys or "(none)")
                return out

            except NodeTimeoutError:
                # Re-raise timeout — do not retry
                return self.result

            except NodeAbortedError:
                raise

            except Exception as exc:
                attempt_elapsed = time.monotonic() - attempt_start
                tb = traceback.format_exc()
                attempt_info = {
                    "attempt": attempt,
                    "error": str(exc),
                    "traceback": tb,
                    "duration": round(attempt_elapsed, 4),
                }
                self.retry_history.append(attempt_info)

                logger.error("  [node]  '%s' | Attempt %d/%d FAILED after %.3f s",
                             self.node_id, attempt, attempts, attempt_elapsed)
                logger.error("  [node]  '%s' |   error_type = %s", self.node_id, type(exc).__name__)
                logger.error("  [node]  '%s' |   error_msg  = %s", self.node_id, exc)

                if attempt < attempts:
                    logger.warning("  [node]  '%s' |   Will retry (%d attempt(s) remaining) ...",
                                   self.node_id, attempts - attempt)
                else:
                    # All attempts exhausted
                    self.status = NodeStatus.FAILED
                    all_tracebacks = "\n---\n".join(
                        f"Attempt {h['attempt']} ({h['duration']}s): {h['error']}\n{h['traceback']}"
                        for h in self.retry_history
                    )
                    logger.error("  [node]  '%s' | All %d attempt(s) exhausted — node FAILED.",
                                 self.node_id, attempts)
                    logger.error("  [node]  '%s' |   total_duration = %.3f s",
                                 self.node_id, time.monotonic() - start)
                    for h in self.retry_history:
                        logger.error("  [node]  '%s' |   attempt %d: %s (%.3fs)",
                                     self.node_id, h["attempt"], h["error"], h["duration"])
                    self.result = {
                        "status": "failed",
                        "error": str(exc),
                        "traceback": all_tracebacks,
                        "retry_attempts": len(self.retry_history),
                    }
                    return self.result

    def serialize(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "node_id": self.node_id,
            "function": self.function_name,
            "function_name": self.function_name,
            "depends_on": self.depends_on,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "config": self.config,
            "metadata": self.metadata,
            "status": self.status.value,
        }
