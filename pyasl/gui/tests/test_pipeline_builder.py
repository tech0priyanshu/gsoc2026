import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from pyasl.gui.views.pipeline_builder_view import PipelineBuilderView
from pyasl.gui.controllers.pipeline_controller import PipelineController

@pytest.fixture
def pipeline_tab(qtbot):
    """Fixture to create and return PipelineBuilderView."""
    ctrl = PipelineController()
    view = PipelineBuilderView(ctrl)
    qtbot.addWidget(view)
    return view, ctrl

def test_pipeline_builder_initialization(pipeline_tab):
    """Verify that the pipeline builder components are properly initialized."""
    view, ctrl = pipeline_tab
    assert view.canvas is not None
    assert view.config_panel is not None
    assert view._new_id is not None
    assert view._new_func is not None

def test_filter_palette(pipeline_tab):
    """Verify that filtering the function palette correctly updates list items."""
    view, _ = pipeline_tab
    view._populate_palette(["asl_prep", "coreg", "normalize", "t1_skull_strip"])
    
    # Filter with "coreg"
    view._on_filter_palette("coreg")
    assert view._palette_list.count() == 1
    assert view._palette_list.item(0).text() == "coreg"

    # Filter case-insensitive
    view._on_filter_palette("PREP")
    assert view._palette_list.count() == 1
    assert view._palette_list.item(0).text() == "asl_prep"

def test_add_node_from_toolbar(pipeline_tab):
    """Verify that typing node details and clicking add updates the graph."""
    view, ctrl = pipeline_tab
    
    view._new_id.setText("node1")
    view._new_func.setText("skull_strip")
    
    view._on_add_node_from_toolbar()
    
    # Check that node is added to graph
    assert "node1" in ctrl.graph.nodes
    assert ctrl.graph.nodes["node1"].function_name == "skull_strip"
    # Fields should be cleared after addition
    assert view._new_id.text() == ""
    assert view._new_func.text() == ""

def test_node_selection_updates_config_panel(pipeline_tab):
    """Verify that selecting a node in the builder loads it into the configuration panel."""
    view, ctrl = pipeline_tab
    
    # Add a node first
    ctrl.add_node("node2", "normalize")
    
    # Select the node
    view._on_node_selected("node2")
    
    # Verify it is loaded in the config panel
    assert view.config_panel._node_id == "node2"

def test_validate_empty_graph(pipeline_tab, monkeypatch):
    """Verify validating an empty graph pops up an info dialog."""
    view, _ = pipeline_tab
    
    info_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", info_mock)
    
    view._on_validate()
    
    assert info_mock.call_count == 1
    assert "No nodes" in info_mock.call_args[0][2]

def test_load_steps_yaml(tmp_path, pipeline_tab):
    """Verify that a pipeline configuration in the standard steps format is loaded correctly."""
    _, ctrl = pipeline_tab
    yaml_content = """
type: pcasl
steps:
  - module: BrukerLoader
    params: { expno: 18, prono: 1 }
  - module: SteadyStateTrim
    params: { trim: 2 }
"""
    cfg_file = tmp_path / "test_steps.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")
    
    ctrl.load_yaml(str(cfg_file))
    
    assert len(ctrl.graph.nodes) == 2
    assert "BrukerLoader" in ctrl.graph.nodes
    assert "SteadyStateTrim" in ctrl.graph.nodes
    assert ctrl.graph.nodes["SteadyStateTrim"].depends_on == ["BrukerLoader"]
    assert ctrl.state.get_config("BrukerLoader") == {"expno": 18, "prono": 1}
    assert ctrl.state.get_config("SteadyStateTrim") == {"trim": 2}

def test_canvas_zoom_and_fit(pipeline_tab):
    """Verify that canvas zoom operations modify the zoom factor and pan offset."""
    view, ctrl = pipeline_tab
    canvas = view.canvas
    
    # Initial state
    assert canvas._zoom_factor == 1.0
    assert canvas._pan_offset.x() == 0
    assert canvas._pan_offset.y() == 0
    
    # Zoom In
    canvas.zoom_in()
    assert canvas._zoom_factor > 1.0
    
    # Zoom Out
    canvas.zoom_out()
    assert canvas._zoom_factor == 1.0
    
    # Add nodes to graph and test zoom fit
    ctrl.add_node("node1", "func1", x=10, y=10)
    ctrl.add_node("node2", "func2", x=500, y=500)
    canvas.zoom_fit()
    
    assert canvas._zoom_factor != 1.0

def test_node_parameter_editing_and_adding(pipeline_tab):
    """Verify editing and adding parameters updates the state config."""
    view, ctrl = pipeline_tab
    
    # Add a node with some initial parameters
    ctrl.add_node("node3", "skull_strip")
    ctrl.state.set_config("node3", {"threshold": 0.5})
    
    # Select node
    view._on_node_selected("node3")
    
    # 1. Edit parameter
    view.config_panel._fields["threshold"].setText("0.25")
    # Trigger textChanged manually since we're setting it programmatically in tests
    view.config_panel._handle_change()
    assert ctrl.state.get_config("node3")["threshold"] == 0.25
    
    # 2. Add parameter
    view.config_panel._new_key_input.setText("clean")
    view.config_panel._new_val_input.setText("true")
    view.config_panel._add_parameter()
    
    # Check that new parameter is in the state config
    assert ctrl.state.get_config("node3")["clean"] is True
    assert ctrl.state.get_config("node3")["threshold"] == 0.25
