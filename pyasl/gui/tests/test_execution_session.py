"""
gui/tests/test_execution_session.py
-------------------------------------
Unit tests for the ExecutionSession model and its integration
with BatchController and MonitorPanelView.
"""
import json
import pytest
from pyasl.gui.models.execution_session import ExecutionSession
from pyasl.gui.controllers.batch_controller import BatchController
from pyasl.gui.views.monitor_panel_view import MonitorPanelView


@pytest.fixture
def execution_session(qtbot):
    session = ExecutionSession()
    return session


def test_execution_session_lifecycle(execution_session):
    """Verify begin, update_job, finalize, and abort lifecycle methods."""
    # 1. Begin session
    execution_session.begin(total_jobs=3)
    assert execution_session.is_running is True
    assert execution_session.total_jobs == 3
    assert execution_session.completed_jobs == 0
    assert execution_session.failed_jobs == 0

    # 2. Job 1 starts & completes
    execution_session.update_job("job_1", "RUNNING", label="Job 1")
    assert execution_session.running_jobs == 1
    assert execution_session.current_job_id == "job_1"

    execution_session.update_job("job_1", "COMPLETED", duration=1.5)
    assert execution_session.running_jobs == 0
    assert execution_session.completed_jobs == 1

    # 3. Job 2 fails
    execution_session.update_job("job_2", "RUNNING", label="Job 2")
    execution_session.update_job("job_2", "FAILED", error="Memory error")
    assert execution_session.failed_jobs == 1

    # 4. Job 3 cached
    execution_session.update_job("job_3", "CACHED", duration=0.1)
    assert execution_session.cached_jobs == 1

    # 5. Finalize
    execution_session.finalize()
    assert execution_session.is_running is False
    assert abs(execution_session.success_rate - 66.666) < 0.1  # 2 completed (1 COMPLETED + 1 CACHED), 1 failed

    stats = execution_session.get_stats()
    assert stats["total"] == 3
    assert stats["completed"] == 2  # 1 COMPLETED + 1 CACHED
    assert stats["failed"] == 1


def test_execution_session_serialization(execution_session):
    """Verify to_dict and from_dict for SessionManager persistence."""
    execution_session.begin(total_jobs=2)
    execution_session.update_job("j1", "COMPLETED", duration=2.0)
    execution_session.update_job("j2", "FAILED", error="Config invalid")
    execution_session.add_log(json.dumps({"level": "INFO", "message": "Done"}))
    execution_session.finalize()

    data = execution_session.to_dict()
    assert data["total_jobs"] == 2
    assert data["completed_jobs"] == 1
    assert data["failed_jobs"] == 1
    assert len(data["timeline_events"]) == 2
    assert len(data["log_entries"]) == 1

    # Restore into new session
    new_session = ExecutionSession()
    new_session.from_dict(data)

    assert new_session.total_jobs == 2
    assert new_session.completed_jobs == 1
    assert new_session.failed_jobs == 1
    assert new_session.has_data is True
    assert len(new_session.log_entries) == 1


def test_monitor_consumes_execution_session_signals(qtbot):
    """Verify that MonitorPanelView automatically updates when ExecutionSession emits signals."""
    session = ExecutionSession()
    monitor = MonitorPanelView()
    qtbot.addWidget(monitor)

    monitor.set_execution_session(session)

    # Start session
    session.begin(total_jobs=2)
    assert monitor._summary._val_labels["total"].text() == "2"

    # Emit job running
    session.update_job("job_x", "RUNNING", label="Subject 01")
    assert monitor._node_stats["job_x"] == "RUNNING"

    # Emit log
    log_json = json.dumps({
        "timestamp": "2026-08-06T12:00:00Z",
        "level": "INFO",
        "node_id": "job_x",
        "message": "Processing slice 10",
    })
    session.add_log(log_json)

    assert len(monitor._log_entries) == 1
    assert "Processing slice 10" in monitor._log_view.toPlainText()

    # Emit job completed
    session.update_job("job_x", "COMPLETED", duration=4.2)
    assert monitor._node_stats["job_x"] == "COMPLETED"

    session.finalize()
    assert monitor._summary._val_labels["completed"].text() == "1"


def test_monitor_restores_from_session(qtbot):
    """Verify that MonitorPanelView restores timeline and logs from an ExecutionSession restored from disk."""
    session = ExecutionSession()
    session.begin(total_jobs=1)
    session.update_job("restored_job", "COMPLETED", duration=3.0)
    session.add_log(json.dumps({"level": "INFO", "message": "Historical log entry"}))
    session.finalize()

    saved_dict = session.to_dict()

    # Create fresh session & monitor
    restored_session = ExecutionSession()
    restored_session.from_dict(saved_dict)

    monitor = MonitorPanelView()
    qtbot.addWidget(monitor)
    monitor.set_execution_session(restored_session)
    monitor.restore_from_session()

    assert monitor._node_stats.get("restored_job") == "COMPLETED"
    assert "Historical log entry" in monitor._log_view.toPlainText()
    assert monitor._summary._val_labels["completed"].text() == "1"


def test_monitor_sync_button(qtbot):
    """Verify that clicking the Sync button rebuilds Monitor state from BatchController jobs."""
    from pyasl.gui.models.batch_state import BatchJob

    session = ExecutionSession()
    monitor = MonitorPanelView()
    qtbot.addWidget(monitor)

    monitor.set_execution_session(session)

    # Mock BatchController with two jobs
    job1 = BatchJob(data_dir="/fake/dir1", config_path="/fake/cfg1.yaml", job_id="sync_j1", label="Sync Job 1")
    job1.status = "COMPLETED"
    job1.duration = 2.5

    job2 = BatchJob(data_dir="/fake/dir2", config_path="/fake/cfg2.yaml", job_id="sync_j2", label="Sync Job 2")
    job2.status = "FAILED"
    job2.error = "Data missing"

    class DummyBatchCtrl:
        class State:
            def __init__(self, jobs):
                self.jobs = jobs
        def __init__(self, jobs):
            self.state = self.State(jobs)

    dummy_ctrl = DummyBatchCtrl([job1, job2])
    monitor.set_batch_controller(dummy_ctrl)

    # Click Sync button
    monitor._sync_btn.click()

    # Verify Monitor UI has been populated with sync_j1 and sync_j2 data
    assert monitor._summary._val_labels["total"].text() == "2"
    assert monitor._summary._val_labels["completed"].text() == "1"
    assert monitor._summary._val_labels["failed"].text() == "1"
    assert monitor._node_stats.get("sync_j1") == "COMPLETED"
    assert monitor._node_stats.get("sync_j2") == "FAILED"

    # Verify logs are populated in log view
    log_text = monitor._log_view.toPlainText()
    assert "sync_j1" in log_text
    assert "sync_j2" in log_text
    assert "Data missing" in log_text

