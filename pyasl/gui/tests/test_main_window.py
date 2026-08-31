import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt

def test_main_window_initialization(main_window):
    """Verify that MainWindow initializes with the correct title, size, and tabs."""
    assert main_window.windowTitle().startswith("PyASL")
    assert main_window.width() == 1280
    assert main_window.height() == 800

    # Verify that the tabs are set up correctly
    tabs = main_window._tabs
    assert tabs is not None
    assert tabs.count() == 5
    assert "Pipeline Builder" in tabs.tabText(0)
    assert "Batch Mode" in tabs.tabText(1)
    assert "Monitor" in tabs.tabText(2)
    assert "Results" in tabs.tabText(3)
    assert "Settings" in tabs.tabText(4)

def test_main_window_tab_navigation(main_window):
    """Verify that we can switch tabs programmatically/via index."""
    tabs = main_window._tabs
    
    # Set to tab index 0
    tabs.setCurrentIndex(0)
    assert tabs.currentIndex() == 0
    
    # Change to settings tab (index 3)
    tabs.setCurrentIndex(3)
    assert tabs.currentIndex() == 3

def test_main_window_about_dialog(main_window, monkeypatch):
    """Verify that clicking the About option opens the custom QMessageBox."""
    exec_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "exec", exec_mock)
    
    main_window._show_about()
    
    # Verify that exec was called (meaning dialog was shown)
    assert exec_mock.call_count == 1

def test_main_window_theme_switching(main_window):
    """Verify that we can change themes programmatically via set_theme."""
    main_window.set_theme("light")
    from pyasl.gui.constants import Colors
    assert Colors.BG_PRIMARY == "#f8fafc"
    
    main_window.set_theme("dark")
    assert Colors.BG_PRIMARY == "#000000"
    
    main_window.set_theme("system")


def test_main_window_application_reset(main_window, tmp_path):
    """Verify that MainWindow application reset clears pipeline, batch, results and restores theme."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "asl.nii").write_text("dummy")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("nodes: []\n")

    main_window._batch_ctrl.add_job(str(data_dir), str(config_file))
    main_window.set_theme("light")

    assert len(main_window._batch_ctrl.state.jobs) > 0

    # Emit reset_requested signal from settings controller
    main_window._settings_ctrl.reset_requested.emit()

    assert len(main_window._batch_ctrl.state.jobs) == 0
    from pyasl.gui.constants import Colors
    assert Colors.BG_PRIMARY == "#000000"  # Restored to dark


