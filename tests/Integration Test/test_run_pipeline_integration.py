import sys
import types
from pathlib import Path
import pytest

from pyasl.pipelines.run_pipeline import run_pipeline


def test_valid_dataset_execution(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("type: custom\n")

    # Inject a fake pipeline module into sys.modules so importlib finds it
    mod_name = "pyasl.pipelines.custom_pipeline"
    mod = types.ModuleType(mod_name)

    def run_custom_pipeline(input_dir, config_path):
        return {"ok": True}

    mod.run_custom_pipeline = run_custom_pipeline
    sys.modules[mod_name] = mod

    try:
        res = run_pipeline(str(data_dir), str(cfg))
        assert res == {"ok": True}
    finally:
        sys.modules.pop(mod_name, None)


def test_missing_dataset_path_raises(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("type: custom\n")
    with pytest.raises(FileNotFoundError):
        run_pipeline(str(tmp_path / "no_such_dir"), str(cfg))


def test_missing_config_file_raises(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        run_pipeline(str(data_dir), str(tmp_path / "no_cfg.yaml"))


def test_invalid_yaml_config_raises(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = tmp_path / "cfg.yaml"
    # YAML list instead of mapping
    cfg.write_text("- item\n- other\n")
    with pytest.raises(ValueError):
        run_pipeline(str(data_dir), str(cfg))


def test_unknown_pipeline_type_raises(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("type: definitely_missing\n")
    with pytest.raises(ValueError):
        run_pipeline(str(data_dir), str(cfg))
