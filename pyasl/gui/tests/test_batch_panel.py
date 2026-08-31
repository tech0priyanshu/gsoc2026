import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from pyasl.gui.views.batch_panel_view import BatchPanelView
from pyasl.gui.controllers.batch_controller import BatchController
from pyasl.gui.models.batch_state import BatchJob

@pytest.fixture
def batch_tab(qtbot):
    """Fixture to create and return BatchPanelView."""
    ctrl = BatchController()
    view = BatchPanelView(ctrl)
    qtbot.addWidget(view)
    return view, ctrl

def test_batch_panel_initialization(batch_tab):
    """Verify that batch panel components are properly initialized."""
    view, ctrl = batch_tab
    assert view._table is not None
    assert view._workers_spin is not None
    assert view._run_btn is not None
    assert view._abort_btn is not None

def test_add_job_simulated(batch_tab, monkeypatch, tmp_path):
    """Verify that adding a job updates both the controller state and the UI table."""
    view, ctrl = batch_tab
    data_dir = str(tmp_path / "data")
    import os
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "test.nii"), "w") as f:
        f.write("dummy")
    cfg_file = str(tmp_path / "config.yaml")
    with open(cfg_file, "w") as f:
        f.write("steps:\n  - id: step_1\n    function: dummy\n")

    # Mock file dialogs to simulate selecting directories/files
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: data_dir
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (cfg_file, "YAML Files (*.yaml *.yml)")
    )
    
    view._on_add_job()
    
    # Verify that the job is in the controller
    assert len(ctrl.state.jobs) == 1
    job = ctrl.state.jobs[0]
    assert job.data_dir == data_dir
    assert job.config_path == cfg_file

    # Verify that the job is added to the UI table
    assert view._table.rowCount() == 1
    assert view._table.item(0, 1).text() == "data"
    assert view._table.item(0, 2).text() == data_dir
    assert view._table.item(0, 3).text() == "config.yaml"

def test_clear_all_jobs(batch_tab, monkeypatch, tmp_path):
    """Verify that clicking clear all removes all jobs from the state and UI."""
    view, ctrl = batch_tab
    data_dir = str(tmp_path / "data")
    import os
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "test.nii"), "w") as f:
        f.write("dummy")
    cfg_file = str(tmp_path / "config.yaml")
    with open(cfg_file, "w") as f:
        f.write("steps:\n  - id: step_1\n    function: dummy\n")
    
    # Mock file dialogs to add a job
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: data_dir)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (cfg_file, ""))
    view._on_add_job()
    assert view._table.rowCount() == 1

    # Trigger clear
    view._ctrl.clear()
    assert view._table.rowCount() == 0
    assert len(ctrl.state.jobs) == 0

def test_workers_spinbox_value(batch_tab):
    """Verify that we can change the spinbox workers value."""
    view, _ = batch_tab
    view._workers_spin.setValue(5)
    assert view._workers_spin.value() == 5


