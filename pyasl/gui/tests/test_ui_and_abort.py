import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication
from pyasl.gui.views.main_window import MainWindow
from pyasl.gui.controllers.batch_controller import BatchController
from pyasl.gui.threads.batch_worker import BatchWorkerThread
from pyasl.batch.job import BatchJob


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_pk1_requires_python_version():
    """Verify PK-1: pyproject.toml specifies requires-python >= 3.10."""
    pyproject_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "pyproject.toml"
    )
    with open(pyproject_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'requires-python = ">=3.10"' in content


def test_cf2_batch_abort_uses_engine_abort():
    """Verify CF-2: BatchWorkerThread.abort calls engine.abort()."""
    job = BatchJob(data_dir="/tmp/test_dir", config_path="pipeline.yaml")
    worker = BatchWorkerThread([job])
    assert hasattr(worker, "abort")
    assert worker._engine._abort_event.is_set() is False
    worker.abort()
    assert worker._engine._abort_event.is_set() is True


def test_gui1_workspace_title_and_icon(qapp):
    """Verify GUI-1: Window title contains workspace name and icon is set."""
    window = MainWindow()
    assert "PyASL -" in window.windowTitle()
    assert not window.windowIcon().isNull()


def test_gui2_no_empty_appearance_menu(qapp):
    """Verify GUI-2: Empty Appearance submenu is removed from menu bar."""
    window = MainWindow()
    mb = window.menuBar()
    
    # Check top level View menu submenus
    for action in mb.actions():
        menu = action.menu()
        if menu and menu.title() == "View":
            titles = [sub.title().strip() for sub in menu.findChildren(object) if hasattr(sub, "title")]
            assert "Appearance" not in titles
