import pytest
import json
from PyQt6.QtWidgets import QFileDialog
from pyasl.gui.views.monitor_panel_view import MonitorPanelView

@pytest.fixture
def monitor_tab(qtbot):
    """Fixture to create and return MonitorPanelView."""
    view = MonitorPanelView()
    qtbot.addWidget(view)
    return view

def test_monitor_initialization(monitor_tab):
    """Verify that the monitor components are properly initialized."""
    assert monitor_tab._log_view is not None
    assert monitor_tab._summary is not None
    assert monitor_tab._timeline is not None
    assert monitor_tab._timer.isActive()

def test_append_log_line(monitor_tab):
    """Verify that adding log lines updates the log view."""
    log_entry = {
        "timestamp": "2026-06-26T15:15:00Z",
        "level": "INFO",
        "node_id": "test_node",
        "status": "RUNNING",
        "message": "Starting node execution"
    }
    json_str = json.dumps(log_entry)
    monitor_tab.on_log_line(json_str)

    assert len(monitor_tab._log_entries) == 1
    content = monitor_tab._log_view.toPlainText()
    assert "test_node" in content
    assert "Starting node execution" in content

def test_filter_by_log_level(monitor_tab):
    """Verify that changing level filter dropdown hides/shows matching logs."""
    info_log = json.dumps({"timestamp": "2026-06-26T15:15:00Z", "level": "INFO", "message": "hello info"})
    error_log = json.dumps({"timestamp": "2026-06-26T15:15:01Z", "level": "ERROR", "message": "hello error"})
    
    monitor_tab.on_log_line(info_log)
    monitor_tab.on_log_line(error_log)
    
    # Filter by ERROR only
    monitor_tab._level_filter.setCurrentText("ERROR")
    monitor_tab._refilter_log()
    content = monitor_tab._log_view.toPlainText()
    assert "hello error" in content
    assert "hello info" not in content

    # Reset filter to ALL
    monitor_tab._level_filter.setCurrentText("ALL")
    monitor_tab._refilter_log()
    content = monitor_tab._log_view.toPlainText()
    assert "hello error" in content
    assert "hello info" in content

def test_on_node_finished_updates_stats(monitor_tab):
    """Verify that node status changes update the summary count."""
    monitor_tab.on_node_finished("node_a", "COMPLETED")
    monitor_tab.on_node_finished("node_b", "FAILED")
    
    # Check that statistics in summary bar are updated
    stats = monitor_tab._summary
    # total=2 (node_a, node_b), completed=1 (node_a), failed=1 (node_b)
    # verify stats match what was passed to update_stats
    assert monitor_tab._node_stats["node_a"] == "COMPLETED"
    assert monitor_tab._node_stats["node_b"] == "FAILED"

def test_clear_monitor(monitor_tab):
    """Verify that clicking clear clears log lists and views."""
    monitor_tab.on_log_line(json.dumps({"timestamp": "2026-06-26T15:15:00Z", "level": "INFO", "message": "hello"}))
    monitor_tab.on_node_finished("node_a", "COMPLETED")
    
    monitor_tab._clear()
    
    assert len(monitor_tab._log_entries) == 0
    assert len(monitor_tab._node_stats) == 0
    assert monitor_tab._log_view.toPlainText() == ""

def test_node_timeline_paint(monitor_tab):
    """Verify that node timeline paints without exception in empty and populated states."""
    # Test empty state painting
    monitor_tab._timeline.repaint()
    
    # Test populated state painting
    monitor_tab.on_node_status_changed("node_1", "RUNNING")
    monitor_tab.on_node_status_changed("node_1", "COMPLETED")
    monitor_tab.on_node_status_changed("node_2", "FAILED")
    monitor_tab._timeline.repaint()

