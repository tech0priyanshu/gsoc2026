"""
tests/test_p4_cancellation.py
-------------------------------
Unit test suite for Priority 4 — Cancellation mechanics:
4A. Pipeline._abort Event & PipelineAbortedError
4B. PipelineWorkerThread.stop() & status="aborted" result
4C. BatchEngine abort & subprocess termination logic
"""
from __future__ import annotations

import time
import pytest

from pyasl.pipeline.pipeline import Pipeline
from pyasl.pipeline.node import Node, NodeStatus
from pyasl.pipeline.exceptions.errors import PipelineAbortedError
from pyasl.batch.engine import BatchEngine
from pyasl.batch.job import BatchJob, BatchStatus


# ======================================================================
# 4A — Pipeline abort flag & PipelineAbortedError
# ======================================================================

class TestPipelineAbort:
    def test_pipeline_abort_before_second_node(self):
        pl = Pipeline(name="abort_test")

        executed = []

        def step1(payload):
            executed.append("n1")
            pl.abort()  # signal abort during node 1 execution
            return {"status": "success"}

        def step2(payload):
            executed.append("n2")
            return {"status": "success"}

        n1 = Node(node_id="n1", function_name="f1")
        n2 = Node(node_id="n2", function_name="f2", depends_on=["n1"])
        n1.function = step1
        n2.function = step2

        pl.add_node(n1)
        pl.add_node(n2)

        with pytest.raises(PipelineAbortedError):
            pl.execute()

        assert executed == ["n1"]
        assert n1.status == NodeStatus.COMPLETED
        assert n2.status == NodeStatus.PENDING

    def test_pipeline_abort_pre_flight(self):
        pl = Pipeline(name="abort_pre_flight")
        n1 = Node(node_id="n1", function_name="f1")
        n1.function = lambda payload: {"status": "success"}
        pl.add_node(n1)

        pl.abort()
        with pytest.raises(PipelineAbortedError):
            pl.execute()


# ======================================================================
# 4B — PipelineWorkerThread abort
# ======================================================================

class TestPipelineWorkerThreadAbort:
    def test_worker_thread_stop_emits_aborted_result(self, qtbot):
        try:
            from pyasl.gui.threads.pipeline_worker import PipelineWorkerThread
        except ImportError:
            pytest.skip("PyQt6 not available")

        pl = Pipeline(name="thread_test")

        def slow_step(payload):
            time.sleep(0.5)
            return {"status": "success"}

        n1 = Node(node_id="n1", function_name="f1")
        n2 = Node(node_id="n2", function_name="f2", depends_on=["n1"])
        n1.function = slow_step
        n2.function = slow_step

        pl.add_node(n1)
        pl.add_node(n2)

        thread = PipelineWorkerThread(pl)

        completed_signal_payload = {}

        def on_done(res):
            nonlocal completed_signal_payload
            completed_signal_payload = res

        thread.pipeline_done.connect(on_done)

        with qtbot.waitSignal(thread.pipeline_done, timeout=5000):
            thread.start()
            qtbot.wait(100)
            thread.stop()

        assert completed_signal_payload.get("status") == "aborted"


# ======================================================================
# 4C — BatchEngine abort
# ======================================================================

class TestBatchEngineAbort:
    def test_batch_engine_abort_skips_pending_jobs(self, tmp_path):
        d1 = tmp_path / "sub1"
        d1.mkdir()
        c1 = tmp_path / "cfg1.yaml"
        c1.write_text("nodes: []\npipeline: {name: p1}")

        d2 = tmp_path / "sub2"
        d2.mkdir()
        c2 = tmp_path / "cfg2.yaml"
        c2.write_text("nodes: []\npipeline: {name: p2}")

        engine = BatchEngine(max_workers=1)
        jobs = [
            BatchJob(job_id="j1", data_dir=str(d1), config_path=str(c1), pipeline_type="dag"),
            BatchJob(job_id="j2", data_dir=str(d2), config_path=str(c2), pipeline_type="dag"),
        ]

        engine.abort()
        results = engine.run(jobs)

        assert len(results) == 2
        assert all(r.status == BatchStatus.ABORTED for r in results)
