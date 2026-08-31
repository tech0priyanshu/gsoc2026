"""
tests/test_t1_gui_pipeline_results.py
---------------------------------------
Integration Test: GUI -> Pipeline -> Results (T-1)

Validates the full GUI pipeline execution flow from loading YAML,
running execution in a background thread (mocked), and automatic
navigation/rendering in the Results tab.
"""
from __future__ import annotations

import os
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

try:
    from PyQt6.QtCore import Qt, pyqtSignal, QObject  # type: ignore
    from PyQt6.QtWidgets import QApplication  # type: ignore
except ImportError:
    pytest.skip("PyQt6 not installed", allow_module_level=True)

from pyasl.gui.views.main_window import MainWindow
from pyasl.gui.controllers.pipeline_controller import PipelineController


class MockWorkerThread(QObject):
    """Mock PipelineWorkerThread that completes synchronously."""
    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str, str)
    pipeline_done = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline

    def start(self):
        # Emit node start, node finished, and pipeline completion
        self.node_started.emit("node_1")
        self.node_finished.emit("node_1", "COMPLETED")
        self.pipeline_done.emit("Pipeline 'gui_pipeline' completed successfully in 0.05s")

    def isRunning(self):
        return False


def test_gui_pipeline_to_results_flow(tmp_path):
    """
    Test GUI pipeline execution to results tab handoff.
    1. Instantiates MainWindow (or controller & results).
    2. Writes a valid 1-node pipeline YAML in tmp_path.
    3. Loads the YAML into PipelineController.
    4. Triggers run with mocked PipelineWorkerThread.
    5. Asserts Results tab receives data and updates UI without blocking main thread.
    """
    # Check if QApplication is available
    app = QApplication.instance() or QApplication([])

    pipeline_data = {
        "pipeline": {"name": "test_integration"},
        "nodes": [
            {
                "id": "node_1",
                "function": "BrukerLoader",
                "depends_on": [],
                "config": {"root": str(tmp_path)}
            }
        ]
    }
    yaml_path = str(tmp_path / "valid_pipeline.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(pipeline_data, f)

    window = MainWindow()

    window._pipeline_ctrl.load_yaml(yaml_path)
    assert len(window._pipeline_ctrl.graph.nodes) == 1
    assert "node_1" in window._pipeline_ctrl.graph.nodes

    completed_messages = []
    window._pipeline_ctrl.run_completed.connect(completed_messages.append)

    with patch("pyasl.pipeline.validator.pre_flight_check", return_value={"valid": True, "errors": [], "nodes_checked": 1}), \
         patch("pyasl.gui.threads.pipeline_worker.PipelineWorkerThread", side_effect=MockWorkerThread):
        
        window._pipeline_ctrl.run()

    assert len(completed_messages) == 1
    assert "completed successfully" in completed_messages[0]
    assert window._results.count() >= 1

    window.close()
