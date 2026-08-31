import sys
import types

import pytest

from pyasl.batch.worker import batch_worker


def test_batch_worker_success(tmp_path):
    # Prepare a fake run_pipeline module so legacy runner returns quickly
    mod_name = "pyasl.pipelines.run_pipeline"
    mod = types.ModuleType(mod_name)

    def run_pipeline(input_dir, config_path):
        return {"ok": True}

    mod.run_pipeline = run_pipeline
    sys.modules[mod_name] = mod

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("type: custom\n")

    try:
        res = batch_worker("j1", str(data_dir), str(cfg), "legacy")
        assert res["status"] == "COMPLETED"
        assert res["result"]["result"]["ok"] is True
    finally:
        sys.modules.pop(mod_name, None)


def test_batch_worker_failure_returns_failed(tmp_path):
    mod_name = "pyasl.pipelines.run_pipeline"
    mod = types.ModuleType(mod_name)

    def run_pipeline(input_dir, config_path):
        raise RuntimeError("boom")

    mod.run_pipeline = run_pipeline
    sys.modules[mod_name] = mod

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("type: custom\n")

    try:
        res = batch_worker("j2", str(data_dir), str(cfg), "legacy")
        assert res["status"] == "FAILED"
        assert "boom" in (res.get("error") or "")
    finally:
        sys.modules.pop(mod_name, None)
