"""
tests/test_t4_batch_mixed.py
------------------------------
Test: Batch with Mixed Success/Failure (T-4)

Validates batch execution fault-isolation where individual failures
do not kill the batch process, and error details are accurately captured.
"""
from __future__ import annotations

import os
from typing import List, Dict
from unittest.mock import patch, MagicMock

import pytest

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not installed", allow_module_level=True)

from pyasl.batch.job import BatchJob, BatchResult, BatchStatus
from pyasl.batch.engine import BatchEngine
from pyasl.gui.controllers.batch_controller import BatchController


def test_batch_engine_mixed_success_failure(tmp_path):
    """
    Test BatchEngine handling 3 jobs with mixed outcomes:
    - Job 1: COMPLETED
    - Job 2: FAILED (RuntimeError)
    - Job 3: COMPLETED
    """
    d1 = tmp_path / "subj1"
    d2 = tmp_path / "subj2"
    d3 = tmp_path / "subj3"
    for d in (d1, d2, d3):
        d.mkdir()
        (d / "data.txt").write_text("sample")

    cfg = tmp_path / "pipeline.yaml"
    cfg.write_text("pipeline:\n  name: test\nnodes:\n  - id: n1\n    function: BrukerLoader\n")

    jobs = [
        BatchJob(data_dir=str(d1), config_path=str(cfg), job_id="job_01"),
        BatchJob(data_dir=str(d2), config_path=str(cfg), job_id="job_02"),
        BatchJob(data_dir=str(d3), config_path=str(cfg), job_id="job_03"),
    ]

    def mock_worker(job_id, data_dir, config_path, pipeline_type):
        if job_id == "job_02":
            return {
                "job_id": job_id,
                "status": "FAILED",
                "start_time": 100.0,
                "end_time": 101.0,
                "result": None,
                "error": "Simulated Processing Error in Job 2",
                "traceback": "Traceback (most recent call last):\n  File 'worker.py', line 10, in batch_worker\nRuntimeError: Simulated Processing Error",
            }
        return {
            "job_id": job_id,
            "status": "COMPLETED",
            "start_time": 100.0,
            "end_time": 102.0,
            "result": {"cbf_mean": 45.2},
            "error": None,
            "traceback": None,
        }

    engine = BatchEngine(max_workers=1)
    with patch("pyasl.batch.engine.batch_worker", side_effect=mock_worker):
        results: List[BatchResult] = engine.run(jobs)

    assert len(results) == 3
    assert results[0].status == BatchStatus.COMPLETED
    assert results[0].result == {"cbf_mean": 45.2}

    assert results[1].status == BatchStatus.FAILED
    assert "Simulated Processing Error in Job 2" in results[1].error
    assert "RuntimeError" in results[1].traceback

    assert results[2].status == BatchStatus.COMPLETED
    assert results[2].result == {"cbf_mean": 45.2}


def test_batch_controller_mixed_results_reporting(tmp_path):
    """
    Test BatchController emitting mixed job results and triggering report.
    """
    app = QApplication.instance() or QApplication([])

    d1 = tmp_path / "subj1"
    d2 = tmp_path / "subj2"
    d3 = tmp_path / "subj3"
    for d in (d1, d2, d3):
        d.mkdir()
        (d / "file.txt").write_text("data")

    cfg = tmp_path / "config.yaml"
    cfg.write_text("pipeline:\n  name: test\nnodes:\n  - id: n1\n    function: BrukerLoader\n")

    ctrl = BatchController()
    j1 = ctrl.add_job(str(d1), str(cfg))
    j2 = ctrl.add_job(str(d2), str(cfg))
    j3 = ctrl.add_job(str(d3), str(cfg))

    mock_results = [
        {"job_id": j1.job_id, "status": "COMPLETED", "duration": 1.5, "data_dir": str(d1), "config_path": str(cfg)},
        {"job_id": j2.job_id, "status": "FAILED", "duration": 0.5, "error": "Disk Read Error", "traceback": "Traceback...", "data_dir": str(d2), "config_path": str(cfg)},
        {"job_id": j3.job_id, "status": "COMPLETED", "duration": 1.2, "data_dir": str(d3), "config_path": str(cfg)},
    ]

    reports = []
    ctrl.report_ready.connect(reports.append)
    ctrl._on_batch_done(mock_results)

    assert len(reports) == 1
    report_path = reports[0]
    assert os.path.exists(report_path)
    assert report_path.endswith(".html")
    assert ctrl.state.get_job(j1.job_id).status == "COMPLETED"
    assert ctrl.state.get_job(j2.job_id).status == "FAILED"
    assert ctrl.state.get_job(j3.job_id).status == "COMPLETED"
