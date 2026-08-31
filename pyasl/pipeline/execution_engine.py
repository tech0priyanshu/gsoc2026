from __future__ import annotations

import logging
import os
import time
from typing import Dict, Any, Optional
from .pipeline import Pipeline
from .execution_context import ExecutionContext
from .config_parser import parse_yaml_file
from .registry import registry
from .logger import pipeline_log, node_log

logger = logging.getLogger("pyasl.pipeline.execution_engine")


def run_pipeline(pipeline: Pipeline, context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
    if context is None:
        context = ExecutionContext()

    # ── Step: Module autodiscovery ────────────────────────────────────────────
    logger.info("  [exec]  Autodiscovering registered modules in 'pyasl.modules' ...")
    try:
        registry.autodiscover("pyasl.modules")
        registered = registry.list_registered() if hasattr(registry, "list_registered") else []
        logger.info("  [exec]  Autodiscovery complete. %d function(s) available in registry.",
                    len(registered))
    except Exception as exc:
        logger.warning("  [exec]  Autodiscovery skipped (non-fatal): %s", exc)

    # ── Step: Execute pipeline ────────────────────────────────────────────────
    node_list = list(pipeline.nodes.keys())
    logger.info("  [exec]  Starting pipeline execution:")
    logger.info("  [exec]    name       = '%s'", pipeline.name)
    logger.info("  [exec]    node_count = %d", len(node_list))
    logger.info("  [exec]    nodes      = %s", node_list)

    t0 = time.time()
    result = pipeline.execute()
    elapsed = time.time() - t0

    # ── Step: Report outcome ──────────────────────────────────────────────────
    status = result.get("status", "unknown")
    nodes_executed = list(result.get("nodes", {}).keys())
    exec_log = result.get("execution_log", [])

    logger.info("  [exec]  Pipeline execution finished:")
    logger.info("  [exec]    status         = %s", status)
    logger.info("  [exec]    elapsed        = %.3f s", elapsed)
    logger.info("  [exec]    nodes_executed = %d", len(nodes_executed))
    if exec_log:
        completed = sum(1 for e in exec_log if e.get("status") == "COMPLETED")
        failed    = sum(1 for e in exec_log if e.get("status") == "FAILED")
        logger.info("  [exec]    completed      = %d  /  failed = %d", completed, failed)

    # emit pipeline-level structured log entry
    _ = pipeline_log({
        "pipeline": pipeline.name,
        "status": result.get("status"),
        "duration": result.get("duration"),
    })
    return result


def run_pipeline_from_yaml(path: str) -> Dict[str, Any]:
    # ── Step: Load config file ────────────────────────────────────────────────
    file_size = os.path.getsize(path) if os.path.isfile(path) else -1
    logger.info("  [exec]  Loading pipeline config from YAML:")
    logger.info("  [exec]    file = %s", os.path.basename(path))
    logger.info("  [exec]    path = %s", path)
    logger.info("  [exec]    size = %d bytes", file_size)

    t0 = time.time()
    pipeline = parse_yaml_file(path)
    parse_ms = (time.time() - t0) * 1000

    # ── Step: Report parsed pipeline structure ────────────────────────────────
    logger.info("  [exec]  YAML parsed successfully in %.1f ms:", parse_ms)
    logger.info("  [exec]    pipeline_name = '%s'", pipeline.name)
    logger.info("  [exec]    total_nodes   = %d", len(pipeline.nodes))
    for i, (nid, node) in enumerate(pipeline.nodes.items(), 1):
        logger.info("  [exec]    node %d/%d | id='%s'  fn='%s'  depends_on=%s  inputs=%s",
                    i, len(pipeline.nodes),
                    nid, node.function_name,
                    node.depends_on or "(none)",
                    list(node.inputs.keys()) or "(none)")

    return run_pipeline(pipeline)
