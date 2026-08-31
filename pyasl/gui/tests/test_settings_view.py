import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from pyasl.gui.views.settings_view import SettingsView
from pyasl.gui.controllers.settings_controller import SettingsController

@pytest.fixture
def settings_tab(qtbot):
    """Fixture to create and return the SettingsView."""
    ctrl = SettingsController()
    view = SettingsView(ctrl)
    qtbot.addWidget(view)
    return view, ctrl

def test_settings_initialization(settings_tab):
    """Verify that settings UI elements are initialized with correct default values."""
    view, ctrl = settings_tab
    assert view._max_workers.value() == ctrl.default_workers
    assert view._log_path.text() == ctrl.log_path

def test_max_workers_changed(settings_tab):
    """Verify that changing the worker count spinbox updates the controller."""
    view, ctrl = settings_tab
    view._max_workers.setValue(4)
    assert ctrl.default_workers == 4

def test_apply_log_file(settings_tab, monkeypatch):
    """Verify that clicking the apply button updates the log file path and triggers info dialog."""
    view, ctrl = settings_tab
    
    # Mock set_log_file and QMessageBox
    set_log_file_mock = MagicMock()
    info_mock = MagicMock()
    monkeypatch.setattr(ctrl, "set_log_file", set_log_file_mock)
    monkeypatch.setattr(QMessageBox, "information", info_mock)
    
    view._log_path.setText("/path/to/my_log.jsonl")
    view._apply_log()
    
    set_log_file_mock.assert_called_once_with("/path/to/my_log.jsonl")

def test_browse_log_file(settings_tab, monkeypatch):
    """Verify that browsing a file updates the line edit text."""
    view, ctrl = settings_tab
    
    # Mock QFileDialog.getSaveFileName to simulate selecting a file
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("/path/to/new_log.jsonl", "JSON Lines (*.jsonl)")
    )
    
    view._browse_log()
    assert view._log_path.text() == "/path/to/new_log.jsonl"


def test_settings_controller_reset():
    """Verify that SettingsController reset_defaults and reset_application work correctly."""
    ctrl = SettingsController()
    ctrl.default_workers = 8
    ctrl._log_path = "/custom/log.jsonl"
    ctrl._theme = "light"

    reset_signal_emitted = []
    ctrl.reset_requested.connect(lambda: reset_signal_emitted.append(True))

    ctrl.reset_application()
    assert ctrl.default_workers == 2
    assert ctrl.theme == "dark"
    assert len(reset_signal_emitted) == 1


def test_reset_application_confirmed(settings_tab, monkeypatch):
    """Verify that confirming application reset triggers controller reset and updates UI fields."""
    view, ctrl = settings_tab

    ctrl.default_workers = 6
    view._max_workers.setValue(6)
    view._log_path.setText("/custom/path.jsonl")

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    info_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", info_mock)

    reset_app_mock = MagicMock(side_effect=ctrl.reset_application)
    monkeypatch.setattr(ctrl, "reset_application", reset_app_mock)

    view._on_reset_application()

    reset_app_mock.assert_called_once()
    assert view._max_workers.value() == 2
    info_mock.assert_called_once()


def test_reset_application_cancelled(settings_tab, monkeypatch):
    """Verify that cancelling application reset does not modify controller or UI settings."""
    view, ctrl = settings_tab

    ctrl.default_workers = 6
    view._max_workers.setValue(6)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    reset_app_mock = MagicMock()
    monkeypatch.setattr(ctrl, "reset_application", reset_app_mock)

    view._on_reset_application()

    reset_app_mock.assert_not_called()
    assert view._max_workers.value() == 6


def test_cache_timer_configured(settings_tab):
    """Verify that 3-second cache refresh timer is configured and active."""
    view, ctrl = settings_tab
    assert hasattr(view, "_cache_timer")
    assert view._cache_timer.isActive()
    assert view._cache_timer.interval() == 3000


def test_cache_size_refresh(settings_tab, tmp_path, qtbot):
    """Verify cache size calculation updates cache size label."""
    view, ctrl = settings_tab
    if hasattr(view, "_size_thread") and view._size_thread is not None:
        view._size_thread.wait(2000)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Write a 1MB file into cache_dir
    dummy_file = cache_dir / "test.dat"
    dummy_file.write_bytes(b"0" * (1024 * 1024))
    
    ctrl._session = MagicMock()
    ctrl._session.cache_dir = str(cache_dir)
    
    view._refresh_cache_size()
    if hasattr(view, "_size_thread") and view._size_thread is not None:
        view._size_thread.wait(2000)
    qtbot.wait(200)
        
    assert "1.00 MB" in view._cache_size_lbl.text()


