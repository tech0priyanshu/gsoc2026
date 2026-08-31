"""
tests/test_t5_yaml_cycles.py
------------------------------
Test: YAML with Cycles (T-5)

Validates DAG cycle detection logic in graph validator and verification
that cyclic pipeline definitions raise CycleDetectedError and report cycle details.
"""
from __future__ import annotations

import pytest
import yaml

from pyasl.pipeline.validator import detect_cycles, validate_pipeline
from pyasl.pipeline.exceptions.errors import CycleDetectedError, InvalidPipelineError
from pyasl.pipeline.config_parser import validate_yaml_config


@pytest.mark.unit
def test_graph_cycle_detection_direct_cycle():
    """
    Test 2-node cycle: A -> B -> A.
    """
    nodes = [
        {"id": "A", "function": "FuncA", "depends_on": ["B"]},
        {"id": "B", "function": "FuncB", "depends_on": ["A"]},
    ]

    with pytest.raises(CycleDetectedError) as exc_info:
        detect_cycles(nodes)

    assert "Cycle detected" in str(exc_info.value)


@pytest.mark.unit
def test_graph_cycle_detection_indirect_cycle():
    """
    Test 3-node cycle: A -> B -> C -> A.
    """
    nodes = [
        {"id": "A", "function": "FuncA", "depends_on": ["C"]},
        {"id": "B", "function": "FuncB", "depends_on": ["A"]},
        {"id": "C", "function": "FuncC", "depends_on": ["B"]},
    ]

    with pytest.raises(CycleDetectedError) as exc_info:
        validate_pipeline(nodes)

    assert "Cycle detected" in str(exc_info.value)


@pytest.mark.unit
def test_yaml_config_parser_with_cycle(tmp_path):
    """
    Test loading YAML containing circular dependency via validate_yaml_config.
    """
    yaml_content = """
pipeline:
  name: cyclic_pipeline
nodes:
  - id: step1
    function: BrukerLoader
    depends_on:
      - step3
  - id: step2
    function: MotionCheck
    depends_on:
      - step1
  - id: step3
    function: DiffImage
    depends_on:
      - step2
"""
    yaml_file = tmp_path / "cyclic_pipeline.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    # Parsing schema succeeds, but graph validation detects cycle
    schema = validate_yaml_config(str(yaml_file))
    nodes_dicts = [n.dict() for n in schema.nodes]

    with pytest.raises(CycleDetectedError):
        detect_cycles(nodes_dicts)


@pytest.mark.integration
def test_pipeline_controller_cycle_surfacing():
    """
    Test that PipelineController.validate() returns cycle error string.
    """
    from pyasl.gui.controllers.pipeline_controller import PipelineController

    ctrl = PipelineController()
    ctrl.add_node("NodeA", "FuncA")
    ctrl.add_node("NodeB", "FuncB")

    # Add cycle: NodeB depends on NodeA, NodeA depends on NodeB
    ctrl.graph.add_edge("NodeA", "NodeB")
    ctrl.graph.add_edge("NodeB", "NodeA")

    err = ctrl.validate()
    assert err is not None
    assert "Cycle detected" in err
