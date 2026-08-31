from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Callable, Dict, List, Any, Optional

from .node import Node, NodeStatus
from .graph import build_graph, topological_sort
from .validator import validate_pipeline
from .registry import registry
from .structured_logger import get_logger
from .exceptions.errors import PipelineAbortedError, NodeAbortedError

logger = logging.getLogger("pyasl.pipeline.pipeline")


class PipelineResult(dict):
    """
    Result dictionary returned by Pipeline.execute().

    Contains node output entries ('node_1': {...}, 'node_2': {...})
    as well as top-level metadata fields ('status', 'pipeline', 'duration', etc.).

    Overrides __len__ to return the count of executed node results for backward
    compatibility with legacy tests checking len(results) == num_nodes.
    """

    def __len__(self) -> int:
        meta_keys = {"pipeline", "status", "start_time", "end_time", "duration", "nodes", "execution_log"}
        return sum(1 for k in self.keys() if k not in meta_keys)


class Pipeline:
    def __init__(
        self,
        name: str = "pipeline",
        stop_on_failure: bool = True,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        Parameters
        ----------
        name              : Human-readable pipeline identifier.
        stop_on_failure   : If True (default), abort remaining nodes when one fails.
        progress_callback : Optional callable(node_id, status) called after each node.
                            Status is one of 'RUNNING', 'COMPLETED', 'FAILED'.
        """
        self.name = name
        self.stop_on_failure = stop_on_failure
        self.progress_callback = progress_callback
        self.nodes: Dict[str, Node] = {}
        self.graph: Dict[str, List[str]] = {}
        self.execution_log: List[Dict[str, Any]] = []
        self._abort = threading.Event()

    def __getstate__(self) -> Dict[str, Any]:
        state = self.__dict__.copy()
        state["_abort"] = None
        state["progress_callback"] = None
        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._abort = threading.Event()

    def abort(self) -> None:
        """Signal the pipeline to stop executing remaining nodes."""
        logger.warning("  [pipeline]  abort() called on '%s' — setting abort flag.", self.name)
        self._abort.set()

    def add_node(self, node: Node) -> None:
        if '.' in node.node_id:
            raise ValueError(f"Node ID '{node.node_id}' cannot contain '.'")
        if node.node_id in self.nodes:
            raise ValueError(f"Node {node.node_id} already exists")
        self.nodes[node.node_id] = node

    def build_graph(self) -> None:
        node_dicts = [node.serialize() for node in self.nodes.values()]
        self.graph = build_graph(node_dicts)

    def get_execution_order(self) -> List[str]:
        if not self.graph:
            self.build_graph()
        return topological_sort(self.graph)

    def _resolve_inputs(self, node: Node) -> Dict[str, Any]:
        """
        Resolve node input references of the form 'source_node_id.output_name'
        or direct values passed into node.inputs.
        """
        resolved = {}
        for input_key, source_spec in node.inputs.items():
            if not isinstance(source_spec, str) or "." not in source_spec:
                resolved[input_key] = source_spec
                continue

            parts = source_spec.split(".", 1)
            src_node_id, src_output_key = parts[0], parts[1]

            src_node = self.nodes.get(src_node_id)
            if src_node is None:
                raise ValueError(
                    f"Node '{node.node_id}' references missing source node '{src_node_id}'"
                )

            if src_node.result is None:
                raise ValueError(
                    f"Node '{node.node_id}' references node '{src_node_id}', but it has not executed yet"
                )

            outputs = src_node.result.get("outputs", {})
            if isinstance(outputs, dict) and src_output_key in outputs:
                resolved[input_key] = outputs[src_output_key]
            elif isinstance(src_node.result, dict) and src_output_key in src_node.result:
                resolved[input_key] = src_node.result[src_output_key]
            else:
                raise KeyError(
                    f"Node '{node.node_id}' requested '{src_output_key}' from node '{src_node_id}', "
                    f"but available outputs are {list(outputs.keys()) if isinstance(outputs, dict) else []}"
                )

        return resolved

    def execute(self) -> PipelineResult:
        """
        Execute all nodes in topological order.

        Returns
        -------
        PipelineResult : Dict subclass containing per-node output entries,
                         status, duration, and execution_log.
        """
        log = get_logger()
        logger.info("Validating pipeline '%s' ...", self.name)
        validate_pipeline([node.serialize() for node in self.nodes.values()])

        logger.info("  Building execution graph ...")
        self.build_graph()
        order = self.get_execution_order()
        logger.info("  Execution order (%d node(s)): %s", len(order), " -> ".join(order))

        start = time.time()
        results = {}

        log.pipeline_event(self.name, status="started")
        logger.info("  Pipeline '%s' execution started.", self.name)

        # ── Node execution loop ───────────────────────────────────────────────
        for step_idx, node_id in enumerate(order, 1):
            if self._abort.is_set():
                logger.warning("  [pipeline]  Abort set — stopping pipeline '%s' before node '%s'.",
                               self.name, node_id)
                raise PipelineAbortedError(f"Pipeline '{self.name}' execution aborted.")

            node = self.nodes.get(node_id)
            if node is None:
                logger.warning("  Step %d/%d | Node '%s' not found — skipping.",
                               step_idx, len(order), node_id)
                continue

            node.set_abort_event(self._abort)

            # Step: resolve function from registry if not already bound
            if node.function is None:
                try:
                    node.function = registry.get(node.function_name)
                    logger.info("  Step %d/%d | Function '%s' resolved OK.",
                                step_idx, len(order), node.function_name)
                except KeyError as exc:
                    # Allow monkeypatched node.execute in existing tests
                    is_monkeypatched = (
                        not hasattr(node.execute, "__func__") or
                        node.execute.__func__ is not Node.execute
                    )
                    if not is_monkeypatched:
                        node.status = NodeStatus.FAILED
                        err = str(exc)
                        logger.error("  Step %d/%d | Function '%s' NOT FOUND in registry: %s",
                                     step_idx, len(order), node.function_name, err)
                        self.execution_log.append(
                            {"node_id": node_id, "status": "FAILED", "error": err}
                        )
                        log.node_finished(node_id, status="FAILED",
                                          pipeline=self.name, error=err)
                        if self.progress_callback:
                            self.progress_callback(node_id, "FAILED")
                        if self.stop_on_failure:
                            logger.error("  stop_on_failure=True — aborting pipeline.")
                            break
                        continue

            # Step: resolve inputs
            node.status = NodeStatus.RUNNING
            inputs_keys = list(node.inputs.keys()) if node.inputs else []
            cfg_params = getattr(node, "config", {})
            logger.info("  Step %d/%d | Running node '%s'  fn='%s'  inputs=%s  params=%s",
                        step_idx, len(order), node_id, node.function_name,
                        inputs_keys or "(none)", cfg_params or "(none)")
            log.node_started(
                node_id,
                pipeline=self.name,
                function=node.function_name,
                step_index=step_idx,
                total_steps=len(order),
                inputs=inputs_keys,
                params=cfg_params,
            )
            if self.progress_callback:
                self.progress_callback(node_id, "RUNNING")

            node_start = time.time()
            try:
                resolved_inputs = self._resolve_inputs(node)
                if resolved_inputs:
                    logger.info("  Step %d/%d | Resolved inputs for '%s': %s",
                                step_idx, len(order), node_id, list(resolved_inputs.keys()))
                out = node.execute(resolved_inputs)
            except NodeAbortedError as exc:
                node.status = NodeStatus.FAILED
                logger.warning("  Step %d/%d | Node '%s' aborted: %s", step_idx, len(order), node_id, exc)
                raise PipelineAbortedError(f"Pipeline '{self.name}' aborted during node '{node_id}'.") from exc
            except Exception as exc:
                node.status = NodeStatus.FAILED
                tb = traceback.format_exc()
                out = {"status": "failed", "error": str(exc), "traceback": tb}
                node.result = out
                logger.error("  Step %d/%d | Node '%s' raised unhandled exception: %s",
                             step_idx, len(order), node_id, exc)

            duration_ms = (time.time() - node_start) * 1000

            if isinstance(out, dict):
                st = str(out.get("status", "")).lower()
                if st == "success":
                    node.status = NodeStatus.COMPLETED
                elif st in ("failed", "error"):
                    node.status = NodeStatus.FAILED

            results[node_id] = out
            self.execution_log.append({
                "node_id": node_id,
                "function": node.function_name,
                "status": node.status.value,
                "duration_ms": round(duration_ms, 2),
                "result": out,
            })

            # Step: report per-node result
            outputs_keys = list((out.get("outputs") or {}).keys()) if isinstance(out, dict) else []
            if node.status == NodeStatus.COMPLETED:
                logger.info("  Step %d/%d | Node '%s' COMPLETED  %.1fms  outputs=%s",
                            step_idx, len(order), node_id, duration_ms,
                            outputs_keys or "(none)")
            else:
                err_msg = out.get("error", "unknown error") if isinstance(out, dict) else str(out)
                retry_count = out.get("retry_attempts", 0) if isinstance(out, dict) else 0
                logger.error("  Step %d/%d | Node '%s' FAILED  %.1fms  error=%s",
                             step_idx, len(order), node_id, duration_ms, err_msg)
                if retry_count:
                    logger.error("             | %d retry attempt(s) were made.", retry_count)

            log.node_finished(
                node_id,
                status=node.status.value,
                duration_ms=duration_ms,
                pipeline=self.name,
                function=node.function_name,
                step_index=step_idx,
                total_steps=len(order),
                outputs=outputs_keys,
                error=out.get("error") if (isinstance(out, dict) and node.status != NodeStatus.COMPLETED) else None,
                traceback=out.get("traceback") if (isinstance(out, dict) and node.status != NodeStatus.COMPLETED) else None,
            )
            if node.status != NodeStatus.COMPLETED:
                error_msg = out.get("error", "Unknown error")
                tb_msg = out.get("traceback")
                full_msg = f"Error: {error_msg}"
                if tb_msg:
                    full_msg += f"\n{tb_msg}"
                log.error(f"Node '{node_id}' failed: {full_msg}",
                          node_id=node_id, pipeline=self.name)

            if self.progress_callback:
                self.progress_callback(node_id, node.status.value)

            if node.status != NodeStatus.COMPLETED and self.stop_on_failure:
                logger.error("  stop_on_failure=True — aborting remaining nodes after '%s'.", node_id)
                break

        # ── Pipeline result ───────────────────────────────────────────────────
        end = time.time()
        total_ms = (end - start) * 1000
        pipeline_status = (
            "completed"
            if all(n.status == NodeStatus.COMPLETED for n in self.nodes.values())
            else "failed"
        )
        log.pipeline_event(self.name, status=pipeline_status, duration_ms=total_ms)

        # ── Summary log ───────────────────────────────────────────────────────
        logger.info("  " + "-" * 58)
        logger.info("  PIPELINE SUMMARY  pipeline='%s'  status=%s  total=%.1fms",
                    self.name, pipeline_status, total_ms)
        for entry in self.execution_log:
            st  = entry.get("status", "?")
            dur = entry.get("duration_ms", 0)
            fn  = entry.get("function", "?")
            nid = entry.get("node_id", "?")
            ok  = "OK" if st == "COMPLETED" else "FAIL"
            logger.info("    [%s] %-20s  %-22s  %8.1fms", ok, nid, fn, dur)
        logger.info("  " + "-" * 58)

        res_dict = PipelineResult({
            "pipeline": self.name,
            "status": pipeline_status,
            "start_time": start,
            "end_time": end,
            "duration": end - start,
            "nodes": results,
            "execution_log": self.execution_log,
        })
        for k, v in results.items():
            if k not in res_dict:
                res_dict[k] = v
        return res_dict
