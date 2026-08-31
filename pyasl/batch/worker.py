"""
batch/worker.py
---------------
Top-level (pickle-safe) worker function for multiprocessing.

Must be a module-level function so ProcessPoolExecutor can pickle it on
Windows. Dispatches to either the DAG engine or the legacy run_pipeline.
"""
from __future__ import annotations

import logging
import os
import time
import traceback
from typing import Any, Dict

logger = logging.getLogger("pyasl.batch.worker")


def _run_dag(job_id: str, data_dir: str, config_path: str) -> Dict[str, Any]:
    """Execute a DAG-style pipeline defined by a YAML config."""
    logger.info("[%s]   >> Importing DAG execution engine ...", job_id)
    from pyasl.pipeline.execution_engine import run_pipeline_from_yaml  # type: ignore

    logger.info("[%s]   >> Calling run_pipeline_from_yaml('%s') ...", job_id, os.path.basename(config_path))
    result = run_pipeline_from_yaml(config_path)

    status = result.get("status", "unknown")
    duration = result.get("duration", 0)
    node_count = len(result.get("nodes", {}))
    logger.info("[%s]   >> DAG execution returned: status=%s  duration=%.3fs  nodes_executed=%d",
                job_id, status, duration, node_count)
    return result


def _run_legacy(job_id: str, data_dir: str, config_path: str) -> Dict[str, Any]:
    """Execute a legacy-style pipeline using the existing run_pipeline dispatcher."""
    logger.info("[%s]   >> Importing legacy run_pipeline ...", job_id)
    from pyasl.pipelines.run_pipeline import run_pipeline  # type: ignore

    logger.info("[%s]   >> Calling run_pipeline(data_dir='%s', config='%s') ...",
                job_id, os.path.basename(data_dir), os.path.basename(config_path))
    result = run_pipeline(data_dir, config_path)

    logger.info("[%s]   >> Legacy pipeline returned.", job_id)
    return {"status": "completed", "result": result}


def batch_worker(
    job_id: str,
    data_dir: str,
    config_path: str,
    pipeline_type: str,
) -> Dict[str, Any]:
    """
    Execute one batch job and return a result dict.

    This function runs in a separate process. It returns a plain dict
    (not a BatchResult) to avoid pickling complex objects across the
    process boundary.

    Returns
    -------
    dict with keys: job_id, status, start_time, end_time, result, error, traceback
    """

    # ─────────────────────────────────────────────────────────────────
    # STEP 1  |  Job received — log all job metadata
    # ─────────────────────────────────────────────────────────────────
    logger.info("=" * 64)
    logger.info("STEP 1  |  JOB RECEIVED")
    logger.info("        |  job_id       = %s", job_id)
    logger.info("        |  pipeline_type= %s", pipeline_type)
    logger.info("        |  data_dir     = %s", data_dir)
    logger.info("        |  config_path  = %s", config_path)
    logger.info("        |  config_size  = %d bytes",
                os.path.getsize(config_path) if os.path.isfile(config_path) else -1)
    logger.info("        |  data_dir_exists = %s", os.path.isdir(data_dir))

    start = time.time()

    try:
        # ─────────────────────────────────────────────────────────────
        # STEP 2  |  Validate paths before dispatching
        # ─────────────────────────────────────────────────────────────
        logger.info("-" * 64)
        logger.info("STEP 2  |  VALIDATING PATHS")
        if not os.path.isdir(data_dir):
            raise FileNotFoundError(f"data_dir does not exist: {data_dir}")
        logger.info("        |  data_dir    : OK  (%d item(s))",
                    len(os.listdir(data_dir)))
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"config_path does not exist: {config_path}")
        logger.info("        |  config_path : OK  (%d bytes)",
                    os.path.getsize(config_path))

        # ─────────────────────────────────────────────────────────────
        # STEP 3  |  Dispatch to correct pipeline engine
        # ─────────────────────────────────────────────────────────────
        logger.info("-" * 64)
        logger.info("STEP 3  |  DISPATCHING TO ENGINE  type='%s'", pipeline_type)

        if pipeline_type == "dag":
            logger.info("        |  Engine selected: DAG (YAML-defined node graph)")
            result = _run_dag(job_id, data_dir, config_path)
        else:
            logger.info("        |  Engine selected: Legacy (run_pipeline dispatcher)")
            result = _run_legacy(job_id, data_dir, config_path)

        # ─────────────────────────────────────────────────────────────
        # STEP 4  |  Job completed successfully
        # ─────────────────────────────────────────────────────────────
        elapsed = time.time() - start
        logger.info("-" * 64)
        logger.info("STEP 4  |  JOB COMPLETED")
        logger.info("        |  job_id  = %s", job_id)
        logger.info("        |  status  = COMPLETED")
        logger.info("        |  elapsed = %.3f s", elapsed)
        logger.info("        |  result_status = %s", result.get("status", "n/a"))
        logger.info("=" * 64)

        return {
            "job_id": job_id,
            "status": "COMPLETED",
            "start_time": start,
            "end_time": time.time(),
            "result": result,
            "error": None,
            "traceback": None,
        }

    except Exception as exc:  # noqa: BLE001
        # ─────────────────────────────────────────────────────────────
        # STEP 4 (failure)  |  Job failed — log full error context
        # ─────────────────────────────────────────────────────────────
        elapsed = time.time() - start
        tb = traceback.format_exc()
        logger.error("-" * 64)
        logger.error("STEP 4  |  JOB FAILED")
        logger.error("        |  job_id        = %s", job_id)
        logger.error("        |  elapsed       = %.3f s", elapsed)
        logger.error("        |  error_type    = %s", type(exc).__name__)
        logger.error("        |  error_message = %s", exc)
        logger.error("        |  traceback:")
        for line in tb.strip().splitlines():
            logger.error("        |    %s", line)
        logger.error("=" * 64)
        return {
            "job_id": job_id,
            "status": "FAILED",
            "start_time": start,
            "end_time": time.time(),
            "result": None,
            "error": str(exc),
            "traceback": tb,
        }
