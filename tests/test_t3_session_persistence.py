"""
tests/test_t3_session_persistence.py
--------------------------------------
Test: Session Save -> Kill -> Restore Cycle (T-3)

Validates state persistence and crash recovery using SessionManager, ensuring
pipeline graphs, node configs, batch jobs, and settings survive application restarts.
"""
from __future__ import annotations

import json
import os
from typing import Dict, Any

import pytest

from pyasl.gui.models.session_manager import SessionManager


def test_session_manager_save_and_restore_cycle(tmp_path):
    """
    Test full save -> simulate crash -> restore cycle with SessionManager.
    """
    workspace_dir = str(tmp_path / "workspace")

    # 1. Initialize SessionManager and populate state
    sm1 = SessionManager(workspace_dir)
    pipeline_data = {
        "nodes": [
            {
                "id": "node_1",
                "function": "BrukerLoader",
                "x": 120,
                "y": 80,
                "depends_on": [],
                "config": {"root": "/path/to/raw"}
            },
            {
                "id": "node_2",
                "function": "MotionCheck",
                "x": 340,
                "y": 80,
                "depends_on": ["node_1"],
                "config": {"threshold": 1.5}
            }
        ]
    }
    batch_jobs_data = []
    settings_data = {
        "theme": "dark",
        "max_workers": 4,
        "log_path": "/var/log/pyasl.log"
    }

    sm1.set_pipeline(pipeline_data)
    sm1.set_batch_jobs(batch_jobs_data)
    sm1.set_settings(settings_data)

    # Save to disk
    sm1.save()
    session_file = sm1.session_path
    assert os.path.exists(session_file)

    # 2. Simulate Hard Crash (delete reference, clear memory)
    del sm1

    # 3. Instantiate Fresh SessionManager and load saved state
    sm2 = SessionManager(workspace_dir)
    ok, missing = sm2.load()
    assert ok is True

    restored_pipeline = sm2.get_pipeline()
    restored_batch = sm2.get_batch_jobs()
    restored_settings = sm2.get_settings()

    # 4. Deep-equal Assertions
    assert restored_pipeline == pipeline_data
    assert len(restored_pipeline["nodes"]) == 2
    assert restored_pipeline["nodes"][0]["config"] == {"root": "/path/to/raw"}
    assert restored_pipeline["nodes"][1]["depends_on"] == ["node_1"]

    assert restored_batch == batch_jobs_data
    assert restored_settings == settings_data
    assert restored_settings["theme"] == "dark"
    assert restored_settings["max_workers"] == 4


def test_session_manager_corrupted_json_recovery(tmp_path):
    """
    Test that corrupted or partial session.json files are handled gracefully.
    """
    workspace_dir = str(tmp_path / "corrupted_ws")
    os.makedirs(workspace_dir, exist_ok=True)
    session_file = os.path.join(workspace_dir, "session.json")

    # Write truncated/invalid JSON
    with open(session_file, "w", encoding="utf-8") as f:
        f.write('{"pipeline": {"nodes": [ {"id": "n1"')

    # SessionManager should catch JSONDecodeError, fallback to default empty state
    sm = SessionManager(workspace_dir)
    ok, _ = sm.load()
    assert ok is False
    assert sm.get_pipeline() == {"nodes": []}
