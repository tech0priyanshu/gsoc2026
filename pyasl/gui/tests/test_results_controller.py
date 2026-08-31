import pytest
from PyQt6.QtWidgets import QApplication
from pyasl.gui.controllers.pipeline_controller import PipelineController
from pyasl.gui.controllers.results_controller import ResultsController


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_add_pipeline_result_single_arg(qapp):
    """Verify add_pipeline_result handles single argument (summary only) without crashing."""
    rc = ResultsController()
    summary = "Pipeline completed | 1.00s | 2 nodes executed"
    
    rc.add_pipeline_result(summary)
    
    assert len(rc.state.results) == 1
    item = rc.state.results[0]
    assert item.name == "Pipeline Execution"
    assert item.type == "pipeline"
    assert item.status == "COMPLETED"
    assert item.summary == summary
    assert item.full_output == summary


def test_add_pipeline_result_two_args(qapp):
    """Verify add_pipeline_result handles two arguments (summary and result_dict)."""
    rc = ResultsController()
    summary = "Pipeline completed successfully"
    result_dict = {"status": "completed", "duration": 2.5}
    
    rc.add_pipeline_result(summary, result_dict)
    
    assert len(rc.state.results) == 1
    item = rc.state.results[0]
    assert item.summary == summary
    assert '"status": "completed"' in item.full_output


def test_pipeline_run_completed_signal_wiring(qapp):
    """Verify PipelineController.run_completed signal connects to ResultsController.add_pipeline_result."""
    pc = PipelineController()
    rc = ResultsController()
    
    pc.run_completed.connect(rc.add_pipeline_result)
    
    # Emit run_completed signal (passes 1 arg: summary)
    summary_str = "Pipeline completed | 0.50s | 1 nodes executed"
    pc.run_completed.emit(summary_str)
    
    assert len(rc.state.results) == 1
    item = rc.state.results[0]
    assert item.summary == summary_str
    assert item.status == "COMPLETED"
