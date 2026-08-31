import pytest

from pyasl.pipeline.graph import build_graph, topological_sort
from pyasl.pipeline.validator import validate_pipeline
from pyasl.pipeline.exceptions.errors import CycleDetectedError, InvalidPipelineError
from pyasl.pipeline.pipeline import Pipeline
from pyasl.pipeline.node import Node
from pyasl.pipeline.registry import register, registry


def test_build_graph_and_toposort():
    nodes = [{"id": "a", "depends_on": []}, {"id": "b", "depends_on": ["a"]}, {"id": "c", "depends_on": ["b"]}]
    g = build_graph(nodes)
    order = topological_sort(g)
    assert order == ["a", "b", "c"]


def test_cycle_detection():
    nodes = [{"id": "a", "depends_on": ["c"]}, {"id": "b", "depends_on": ["a"]}, {"id": "c", "depends_on": ["b"]}]
    with pytest.raises(CycleDetectedError):
        validate_pipeline(nodes)


def test_pipeline_execution_and_data_passing():
    @register("load_data")
    def _load(payload):
        return {"outputs": {"raw_data": "raw"}}

    @register("motion_corr")
    def _motion(payload):
        inputs = payload.get("inputs", {})
        raw = inputs.get("raw_data")
        return {"outputs": {"corrected_data": f"{raw}_corrected"}}

    @register("quantify")
    def _quant(payload):
        inputs = payload.get("inputs", {})
        corr = inputs.get("corrected_data")
        return {"outputs": {"cbf_map": f"{corr}_cbf"}}

    n1 = Node(node_id="import_data", function_name="load_data", outputs=["raw_data"])
    n2 = Node(node_id="motion_correction", function_name="motion_corr", depends_on=["import_data"], inputs={"raw_data": "import_data.raw_data"}, outputs=["corrected_data"])  # type: ignore
    n3 = Node(node_id="quantification", function_name="quantify", depends_on=["motion_correction"], inputs={"corrected_data": "motion_correction.corrected_data"}, outputs=["cbf_map"])  # type: ignore

    pl = Pipeline("test_pipeline")
    pl.add_node(n1)
    pl.add_node(n2)
    pl.add_node(n3)

    res = pl.execute()
    assert res["status"] == "completed"
    assert pl.nodes["quantification"].result["outputs"]["cbf_map"] == "raw_corrected_cbf"
