"""
tests/test_t6_batch_abort.py
------------------------------
Test: Abort During Batch Execution (T-6)

Validates immediate cancellation, state cleanup, and ABORTED status assignment
when a batch job run is aborted mid-execution.
"""
from __future__ import annotations

import time
from typing import List
from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6.QtCore import QObject
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not installed", allow_module_level=True)

from pyasl.batch.job import BatchJob, BatchResult, BatchStatus
from pyasl.batch.engine import BatchEngine
from pyasl.gui.controllers.batch_controller import BatchController


def test_batch_engine_abort_mid_execution(tmp_path):
    """
    Test that calling engine.abort() stops further job submissions
    and sets status to ABORTED.
    """
    jobs = [
        BatchJob(data_dir=str(tmp_path), config_path="cfg.yaml", job_id=f"job_{i}")
        for i in range(5)
    ]

    engine = BatchEngine(max_workers=1)

    def slow_worker(job_id, data_dir, config_path, pipeline_type):
        if job_id == "job_0":
            engine.abort()  # Trigger abort during first job
        return {
            "job_id": job_id,
            "status": "COMPLETED",
            "start_time": 100.0,
            "end_time": 101.0,
            "result": {},
            "error": None,
            "traceback": None,
        }

    with patch("pyasl.batch.engine.batch_worker", side_effect=slow_worker):
        results: List[BatchResult] = engine.run(jobs)

    # First job runs, rest are aborted immediately
    aborted_jobs = [r for r in results if r.status == BatchStatus.ABORTED]
    assert len(aborted_jobs) >= 4
    for r in aborted_jobs:
        assert r.status == BatchStatus.ABORTED


def test_batch_controller_abort_flow(tmp_path):
    """
    Test BatchController.abort() behavior and state updates.
    """
    app = QApplication.instance() or QApplication([])

    d1 = tmp_path / "data1"
    d1.mkdir()
    (d1 / "f.txt").write_text("x")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("pipeline:\n  name: test\nnodes:\n  - id: n\n    function: BrukerLoader\n")

    ctrl = BatchController()
    job = ctrl.add_job(str(d1), str(cfg))

    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    ctrl._worker = mock_worker

    ctrl.abort()

    mock_worker.abort.assert_called_once()
