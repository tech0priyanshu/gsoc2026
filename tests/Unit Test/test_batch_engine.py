import sys
import types
import time
import json
import os
import threading
import pytest

# ---- isolate from heavy pyasl/__init__.py top-level imports ----
# Use absolute paths so the isolation works regardless of cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PYASL_ROOT = os.path.join(_HERE, "..")   # PyASL/
_PYASL_PKG = os.path.join(_PYASL_ROOT, "pyasl")

if _PYASL_ROOT not in sys.path:
    sys.path.insert(0, _PYASL_ROOT)

if "pyasl" not in sys.modules:
    fake = types.ModuleType("pyasl")
    fake.__path__ = [_PYASL_PKG]
    fake.__package__ = "pyasl"
    fake.__spec__ = None
    sys.modules["pyasl"] = fake



# ============================================================
# Test BatchJob
# ============================================================

class TestBatchJob:

    def test_creation_defaults(self):
        from pyasl.batch.job import BatchJob, BatchStatus
        job = BatchJob(data_dir="/data/subj01", config_path="config.yaml")
        assert job.status == BatchStatus.PENDING
        assert job.pipeline_type == "legacy"
        assert len(job.job_id) == 8
        assert job.duration is None

    def test_duration_computed(self):
        from pyasl.batch.job import BatchJob
        job = BatchJob(data_dir="/d", config_path="c.yaml")
        job.start_time = 100.0
        job.end_time = 105.0
        assert abs(job.duration - 5.0) < 0.001

    def test_to_dict_keys(self):
        from pyasl.batch.job import BatchJob
        job = BatchJob(data_dir="/d", config_path="c.yaml", label="test_job")
        d = job.to_dict()
        for key in ["job_id", "label", "data_dir", "config_path",
                    "pipeline_type", "status"]:
            assert key in d


# ============================================================
# Test BatchResult
# ============================================================

class TestBatchResult:

    def test_duration(self):
        from pyasl.batch.job import BatchResult, BatchStatus
        r = BatchResult(
            job_id="abc", status=BatchStatus.COMPLETED,
            data_dir="/d", config_path="c.yaml",
            start_time=1000.0, end_time=1003.5,
        )
        assert abs(r.duration - 3.5) < 0.001

    def test_to_dict(self):
        from pyasl.batch.job import BatchResult, BatchStatus
        r = BatchResult(
            job_id="abc", status=BatchStatus.FAILED,
            data_dir="/d", config_path="c.yaml",
            start_time=1000.0, end_time=1001.0,
            error="boom",
        )
        d = r.to_dict()
        assert d["status"] == "FAILED"
        assert d["error"] == "boom"
        assert d["duration"] == 1.0


# ============================================================
# Test Report Generator
# ============================================================

class TestReportGenerator:

    def test_html_and_json_created(self, tmp_path):
        from pyasl.batch.job import BatchResult, BatchStatus
        from pyasl.batch.report import generate_report

        results = [
            BatchResult("j1", BatchStatus.COMPLETED, "/d1", "c.yaml", 0.0, 1.5),
            BatchResult("j2", BatchStatus.FAILED, "/d2", "c.yaml", 0.0, 0.5, error="crash"),
            BatchResult("j3", BatchStatus.ABORTED, "/d3", "c.yaml", 0.0, 0.0),
        ]
        html_path, json_path = generate_report(results, output_dir=str(tmp_path))

        assert os.path.exists(html_path)
        assert os.path.exists(json_path)

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        assert "COMPLETED" in html
        assert "FAILED" in html
        assert "crash" in html

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["summary"]["total"] == 3
        assert data["summary"]["completed"] == 1
        assert data["summary"]["failed"] == 1

    def test_empty_results(self, tmp_path):
        from pyasl.batch.report import generate_report
        html_path, json_path = generate_report([], output_dir=str(tmp_path))
        assert os.path.exists(html_path)
        with open(json_path) as f:
            data = json.load(f)
        assert data["summary"]["total"] == 0


# ============================================================
# Test BatchEngine (with mock worker)
# ============================================================

class TestBatchEngine:

    def _make_jobs(self, n=2):
        from pyasl.batch.job import BatchJob
        return [
            BatchJob(
                data_dir=f"/fake/subj{i:02d}",
                config_path="fake.yaml",
                job_id=f"job{i:02d}",
                pipeline_type="legacy",
            )
            for i in range(n)
        ]

    def _patch_executor_to_threadpool(self, monkeypatch):
        import concurrent.futures

        monkeypatch.setattr(
            "pyasl.batch.engine.concurrent.futures.ProcessPoolExecutor",
            concurrent.futures.ThreadPoolExecutor,
        )

    def test_empty_batch_returns_empty(self):
        from pyasl.batch.engine import BatchEngine
        engine = BatchEngine(max_workers=1)
        results = engine.run([])
        assert results == []

    def test_abort_flag_behavior(self):
        """abort() sets the internal flag; reset() clears it."""
        from pyasl.batch.engine import BatchEngine
        engine = BatchEngine(max_workers=1)
        assert not engine._abort_event.is_set()
        engine.abort()
        assert engine._abort_event.is_set()
        engine.reset()
        assert not engine._abort_event.is_set()

    def test_abort_skips_pending_before_loop(self):
        """When abort() is called before run(), the abort flag is pre-set
        and all jobs are skipped before submission."""
        from pyasl.batch.engine import BatchEngine, _emit
        from pyasl.batch.job import BatchJob, BatchStatus

        # Patch ProcessPoolExecutor to verify no jobs submitted
        submitted = []
        class FakeExecutor:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def submit(self, fn, *args, **kwargs):
                submitted.append(args[0])  # job_id
                import concurrent.futures
                f = concurrent.futures.Future()
                f.set_exception(RuntimeError("should not run"))
                return f

        import pyasl.batch.engine as eng_mod
        original = eng_mod.concurrent.futures.ProcessPoolExecutor

        class PatchedEngine(BatchEngine):
            def run(self, jobs, progress_callback=None):
                results = {}
                if not jobs:
                    return []
                for job in jobs:
                    if self._abort_event.is_set():
                        job.status = BatchStatus.ABORTED
                        _emit(progress_callback, job.job_id, "ABORTED", None)
                # Collect aborted
                import time as _t
                t = _t.time()
                from pyasl.batch.job import BatchResult
                return [
                    BatchResult(j.job_id, j.status, j.data_dir, j.config_path, t, t)
                    for j in jobs
                ]

        engine = PatchedEngine(max_workers=1)
        engine.abort()
        jobs = self._make_jobs(3)
        results = engine.run(jobs)
        assert len(results) == 3
        for r in results:
            assert r.status == BatchStatus.ABORTED
        assert len(submitted) == 0  # no jobs were actually submitted


    def test_progress_callback_called(self, monkeypatch):
        """Verify progress callback is invoked for each job."""
        self._patch_executor_to_threadpool(monkeypatch)

        def mock_worker(job_id, data_dir, config_path, pipeline_type):
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "start_time": time.time(),
                "end_time": time.time() + 0.01,
                "result": {"status": "completed"},
                "error": None,
                "traceback": None,
            }

        monkeypatch.setattr(
            "pyasl.batch.engine.batch_worker", mock_worker
        )

        calls = []

        def _cb(job_id, status, result):
            calls.append((job_id, status))

        from pyasl.batch.engine import BatchEngine
        engine = BatchEngine(max_workers=2)
        jobs = self._make_jobs(2)
        results = engine.run(jobs, progress_callback=_cb)

        job_ids = {j.job_id for j in jobs}
        cb_ids = {c[0] for c in calls}
        assert job_ids.issubset(cb_ids)

    def test_result_order_matches_input(self, monkeypatch):
        """Results should be in the same order as input jobs."""
        self._patch_executor_to_threadpool(monkeypatch)

        def mock_worker(job_id, data_dir, config_path, pipeline_type):
            time.sleep(0.005)
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "start_time": time.time(),
                "end_time": time.time(),
                "result": None,
                "error": None,
                "traceback": None,
            }

        monkeypatch.setattr("pyasl.batch.engine.batch_worker", mock_worker)

        from pyasl.batch.engine import BatchEngine
        engine = BatchEngine(max_workers=2)
        jobs = self._make_jobs(4)
        results = engine.run(jobs)

        assert len(results) == 4
        for job, result in zip(jobs, results):
            assert result.job_id == job.job_id

    def test_successful_job_execution(self, monkeypatch):
        self._patch_executor_to_threadpool(monkeypatch)

        def mock_worker(job_id, data_dir, config_path, pipeline_type):
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "start_time": time.time(),
                "end_time": time.time() + 0.01,
                "result": {"job": job_id},
                "error": None,
                "traceback": None,
            }

        monkeypatch.setattr("pyasl.batch.engine.batch_worker", mock_worker)

        from pyasl.batch.engine import BatchEngine
        engine = BatchEngine(max_workers=2)
        jobs = self._make_jobs(3)
        results = engine.run(jobs)

        assert len(results) == 3
        assert all(r.status.name == "COMPLETED" for r in results)
        assert [r.job_id for r in results] == [j.job_id for j in jobs]
        assert all(r.result["job"] == j.job_id for r, j in zip(results, jobs))

    def test_worker_exception_handling(self, monkeypatch):
        self._patch_executor_to_threadpool(monkeypatch)

        def broken_worker(job_id, data_dir, config_path, pipeline_type):
            raise RuntimeError("boom")

        monkeypatch.setattr("pyasl.batch.engine.batch_worker", broken_worker)

        from pyasl.batch.engine import BatchEngine, BatchStatus
        engine = BatchEngine(max_workers=2)
        jobs = self._make_jobs(2)
        results = engine.run(jobs)

        assert len(results) == 2
        assert all(r.status == BatchStatus.FAILED for r in results)
        assert all("boom" in (r.error or "") for r in results)

    def test_fault_isolation(self, monkeypatch):
        self._patch_executor_to_threadpool(monkeypatch)

        def flaky_worker(job_id, data_dir, config_path, pipeline_type):
            if job_id.endswith("01"):
                raise ValueError("failure")
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "start_time": time.time(),
                "end_time": time.time() + 0.01,
                "result": {"ok": True},
                "error": None,
                "traceback": None,
            }

        monkeypatch.setattr("pyasl.batch.engine.batch_worker", flaky_worker)

        from pyasl.batch.engine import BatchEngine, BatchStatus
        engine = BatchEngine(max_workers=2)
        jobs = self._make_jobs(3)
        results = engine.run(jobs)

        assert len(results) == 3
        assert results[0].status == BatchStatus.COMPLETED
        assert results[1].status == BatchStatus.FAILED
        assert results[2].status == BatchStatus.COMPLETED

    def test_multiple_jobs_with_limited_workers(self, monkeypatch):
        self._patch_executor_to_threadpool(monkeypatch)
        lock = threading.Lock()
        running = 0
        max_seen = 0

        def worker(job_id, data_dir, config_path, pipeline_type):
            nonlocal running, max_seen
            with lock:
                running += 1
                max_seen = max(max_seen, running)
            time.sleep(0.02)
            with lock:
                running -= 1
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "start_time": time.time(),
                "end_time": time.time(),
                "result": {"ok": True},
                "error": None,
                "traceback": None,
            }

        monkeypatch.setattr("pyasl.batch.engine.batch_worker", worker)

        from pyasl.batch.engine import BatchEngine
        engine = BatchEngine(max_workers=2)
        jobs = self._make_jobs(5)
        results = engine.run(jobs)

        assert len(results) == 5
        assert max_seen == 2
        assert all(r.status.name == "COMPLETED" for r in results)

    def test_large_job_queue(self, monkeypatch):
        self._patch_executor_to_threadpool(monkeypatch)

        def worker(job_id, data_dir, config_path, pipeline_type):
            return {
                "job_id": job_id,
                "status": "COMPLETED",
                "start_time": time.time(),
                "end_time": time.time(),
                "result": {"ok": True},
                "error": None,
                "traceback": None,
            }

        monkeypatch.setattr("pyasl.batch.engine.batch_worker", worker)

        from pyasl.batch.engine import BatchEngine
        engine = BatchEngine(max_workers=4)
        jobs = self._make_jobs(20)
        results = engine.run(jobs)

        assert len(results) == 20
        assert all(r.status.name == "COMPLETED" for r in results)

    def test_mixed_success_and_failure_scenarios(self, monkeypatch):
        self._patch_executor_to_threadpool(monkeypatch)

        def worker(job_id, data_dir, config_path, pipeline_type):
            if int(job_id[-2:]) % 2 == 0:
                return {
                    "job_id": job_id,
                    "status": "COMPLETED",
                    "start_time": time.time(),
                    "end_time": time.time(),
                    "result": {"ok": True},
                    "error": None,
                    "traceback": None,
                }
            raise RuntimeError("job failure")

        monkeypatch.setattr("pyasl.batch.engine.batch_worker", worker)

        from pyasl.batch.engine import BatchEngine, BatchStatus
        engine = BatchEngine(max_workers=3)
        jobs = self._make_jobs(6)
        results = engine.run(jobs)

        assert len(results) == 6
        assert sum(1 for r in results if r.status == BatchStatus.COMPLETED) == 3
        assert sum(1 for r in results if r.status == BatchStatus.FAILED) == 3
