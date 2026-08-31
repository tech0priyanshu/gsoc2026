"""
tests/test_process_architecture.py
-----------------------------------
Unit tests for PyASL process architecture, process identity naming,
and process-isolated worker thread execution.
"""
import os
import sys
import time
import pytest

from pyasl.gui.utils.process_helper import set_process_identity, get_worker_executable, is_frozen
from pyasl.batch import BatchEngine, BatchJob
from pyasl.pipeline.pipeline import Pipeline
from pyasl.pipeline.node import Node
from pyasl.gui.threads.pipeline_worker import PipelineWorkerThread


def test_process_helper_identity():
    """Verify set_process_identity updates process name without error."""
    set_process_identity("PyASL Test Worker")
    import multiprocessing
    assert multiprocessing.current_process().name == "PyASL Test Worker"


def test_get_worker_executable():
    """Verify get_worker_executable returns valid executable string."""
    exe = get_worker_executable("PyASL Processing")
    assert isinstance(exe, str)
    assert len(exe) > 0


def dummy_node_fn(payload):
    """Simple dummy function for testing node execution."""
    cfg = payload.get("config", {}) if isinstance(payload, dict) else {}
    return {"status": "success", "value": cfg.get("val", 42)}


def test_pipeline_worker_thread_process_isolation(qtbot):
    """Verify PipelineWorkerThread executes pipeline and emits signals."""
    pl = Pipeline("test_isolated_pipeline")
    n1 = Node(node_id="n1", function_name="dummy", config={"val": 100})
    n1.function = dummy_node_fn
    pl.add_node(n1)

    worker = PipelineWorkerThread(pl)
    
    signals_received = {
        "started": [],
        "finished": [],
        "done": [],
        "error": [],
    }

    worker.node_started.connect(lambda nid: signals_received["started"].append(nid))
    worker.node_finished.connect(lambda nid, st: signals_received["finished"].append((nid, st)))
    worker.pipeline_done.connect(lambda res: signals_received["done"].append(res))
    worker.error_occurred.connect(lambda err: signals_received["error"].append(err))

    with qtbot.waitSignal(worker.pipeline_done, timeout=5000):
        worker.start()

    worker.wait(3000)

    assert len(signals_received["done"]) == 1
    res = signals_received["done"][0]
    assert res["status"] == "completed"
    assert "n1" in res["nodes"]
    assert len(signals_received["started"]) >= 1


def failing_node_fn(payload):
    """Dummy node function that raises an exception."""
    raise ValueError("Simulated pipeline failure")


def test_pipeline_worker_thread_error_handling(qtbot):
    """Verify exception inside worker pipeline is propagated via error_occurred signal."""
    pl = Pipeline("test_failing_pipeline")
    f1 = Node(node_id="f1", function_name="failing", config={}, max_retries=0)
    f1.function = failing_node_fn
    pl.add_node(f1)

    worker = PipelineWorkerThread(pl)
    errors = []
    worker.error_occurred.connect(errors.append)

    with qtbot.waitSignal(worker.error_occurred, timeout=5000):
        worker.start()

    worker.wait(3000)

    assert len(errors) == 1
    assert "Simulated pipeline failure" in errors[0]
