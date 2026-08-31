"""
Tests for SessionManager.

Covers save/load round-trip, missing-file detection, corrupted JSON
recovery, and version migration.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from pyasl.gui.models.session_manager import SessionManager, SESSION_VERSION


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return str(ws)


@pytest.fixture
def session(workspace):
    """Create a SessionManager backed by a temp workspace."""
    return SessionManager(workspace_root=workspace)


class TestWorkspaceInit:
    def test_creates_subdirectories(self, workspace):
        sm = SessionManager(workspace_root=workspace)
        assert os.path.isdir(os.path.join(workspace, "uploads"))
        assert os.path.isdir(os.path.join(workspace, "cache"))
        assert os.path.isdir(os.path.join(workspace, "logs"))

    def test_properties(self, session, workspace):
        assert session.workspace_root == workspace
        assert session.cache_dir == os.path.join(workspace, "cache")
        assert session.uploads_dir == os.path.join(workspace, "uploads")
        assert session.logs_dir == os.path.join(workspace, "logs")
        assert session.session_path == os.path.join(workspace, "session.json")


class TestSaveLoad:
    def test_save_creates_file(self, session):
        session.save()
        assert os.path.isfile(session.session_path)

    def test_round_trip_empty(self, session):
        session.save()
        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success is True
        assert missing == []

    def test_round_trip_with_batch_jobs(self, session, tmp_path):
        # Create real directories/files so validation passes
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)
        config_path = str(tmp_path / "config.yaml")
        with open(config_path, "w") as f:
            f.write("steps: []\n")

        jobs = [
            {
                "job_id": "abc123",
                "label": "test_job",
                "data_dir": data_dir,
                "config_path": config_path,
                "pipeline_type": "legacy",
                "status": "COMPLETED",
                "duration": 1.5,
            }
        ]
        session.set_batch_jobs(jobs)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success is True
        assert missing == []
        restored = sm2.get_batch_jobs()
        assert len(restored) == 1
        assert restored[0]["job_id"] == "abc123"
        assert restored[0]["status"] == "COMPLETED"

    def test_round_trip_with_pipeline(self, session):
        pipeline = {
            "nodes": [
                {
                    "node_id": "n1",
                    "function_name": "BrukerLoader",
                    "x": 40,
                    "y": 40,
                    "depends_on": [],
                    "config": {"key": "val"},
                }
            ]
        }
        session.set_pipeline(pipeline)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, _ = sm2.load()
        assert success
        restored = sm2.get_pipeline()
        assert len(restored["nodes"]) == 1
        assert restored["nodes"][0]["node_id"] == "n1"

    def test_round_trip_settings(self, session):
        session.set_settings({
            "log_path": "/tmp/test.jsonl",
            "default_workers": 4,
            "theme": "light",
        })

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, _ = sm2.load()
        assert success
        settings = sm2.get_settings()
        assert settings["default_workers"] == 4
        assert settings["theme"] == "light"

    def test_update_setting(self, session):
        session.update_setting("theme", "light")
        session.update_setting("default_workers", 8)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, _ = sm2.load()
        assert success
        settings = sm2.get_settings()
        assert settings["theme"] == "light"
        assert settings["default_workers"] == 8


class TestMissingFiles:
    def test_detects_missing_data_dir(self, session, tmp_path):
        config_path = str(tmp_path / "config.yaml")
        with open(config_path, "w") as f:
            f.write("steps: []\n")

        jobs = [
            {
                "job_id": "miss1",
                "label": "missing_job",
                "data_dir": "/nonexistent/path/data",
                "config_path": config_path,
                "pipeline_type": "legacy",
                "status": "PENDING",
            }
        ]
        session.set_batch_jobs(jobs)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success is True
        assert len(missing) == 1
        assert missing[0]["job_id"] == "miss1"
        # Valid jobs should be empty since the only job had missing data
        assert sm2.get_batch_jobs() == []

    def test_detects_missing_config(self, session, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)

        jobs = [
            {
                "job_id": "miss2",
                "label": "missing_config",
                "data_dir": data_dir,
                "config_path": "/nonexistent/config.yaml",
                "pipeline_type": "legacy",
                "status": "PENDING",
            }
        ]
        session.set_batch_jobs(jobs)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success
        assert len(missing) == 1
        assert sm2.get_batch_jobs() == []

    def test_keeps_valid_removes_invalid(self, session, tmp_path):
        # Valid job
        data_dir_ok = str(tmp_path / "data_ok")
        os.makedirs(data_dir_ok, exist_ok=True)
        config_ok = str(tmp_path / "config_ok.yaml")
        with open(config_ok, "w") as f:
            f.write("steps: []\n")

        jobs = [
            {
                "job_id": "good",
                "data_dir": data_dir_ok,
                "config_path": config_ok,
            },
            {
                "job_id": "bad",
                "data_dir": "/nonexistent",
                "config_path": "/also_nonexistent",
            },
        ]
        session.set_batch_jobs(jobs)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success
        assert len(missing) == 1
        valid = sm2.get_batch_jobs()
        assert len(valid) == 1
        assert valid[0]["job_id"] == "good"


class TestErrorRecovery:
    def test_corrupted_json(self, session):
        # Write garbage to session.json
        with open(session.session_path, "w") as f:
            f.write("{{{invalid json")

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success is False
        assert missing == []

    def test_non_dict_json(self, session):
        with open(session.session_path, "w") as f:
            json.dump([1, 2, 3], f)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success is False

    def test_version_mismatch(self, session):
        with open(session.session_path, "w") as f:
            json.dump({"version": 999, "batch_jobs": []}, f)

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, missing = sm2.load()
        assert success is False  # No migration from v999


class TestReset:
    def test_reset_clears_data(self, session, tmp_path):
        data_dir = str(tmp_path / "data")
        os.makedirs(data_dir, exist_ok=True)
        config = str(tmp_path / "c.yaml")
        with open(config, "w") as f:
            f.write("")

        session.set_batch_jobs([
            {"job_id": "x", "data_dir": data_dir, "config_path": config}
        ])
        session.reset()

        sm2 = SessionManager(workspace_root=session.workspace_root)
        success, _ = sm2.load()
        assert success is True
        assert sm2.get_batch_jobs() == []
        assert sm2.get_pipeline() == {"nodes": []}


class TestSessionExists:
    def test_no_file(self, workspace):
        sm = SessionManager(workspace_root=workspace)
        # Before first save, session_exists depends on whether
        # __init__ creates the file — it does not.
        # Actually _init_workspace doesn't create session.json
        assert sm.session_exists() is False

    def test_after_save(self, session):
        session.save()
        assert session.session_exists() is True
