"""
tests/test_t2_core_modules.py
-------------------------------
Unit Tests for 5 Core Processing Modules (T-2)

Dedicated test classes with >90% coverage target, testing Happy Path, Edge Cases,
and Failure/Exception scenarios via @pytest.mark.parametrize for:
1. YAMLParser (config_parser.py)
2. GraphValidator (validator.py)
3. PipelineExecutionEngine (pipeline.py)
4. CacheManager (cache_manager.py)
5. ReportGenerator (report.py)
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Any
from unittest.mock import MagicMock, patch

import pytest

from pyasl.pipeline.config_parser import validate_yaml_config, parse_yaml_file
from pyasl.pipeline.validator import validate_pipeline, pre_flight_check
from pyasl.pipeline.pipeline import Pipeline
from pyasl.pipeline.node import Node, NodeStatus
from pyasl.pipeline.exceptions.errors import InvalidPipelineError, CycleDetectedError
from pyasl.gui.models.cache_manager import CacheManager
from pyasl.batch.report import generate_report
from pyasl.batch.job import BatchResult, BatchStatus


# =============================================================================
# 1. TestYAMLParser
# =============================================================================
class TestYAMLParser:
    """Test suite for YAMLParser / validate_yaml_config."""

    @pytest.mark.parametrize(
        "content, expected_node_count, expected_first_id",
        [
            ("pipeline:\n  name: p1\nnodes:\n  - id: n1\n    function: BrukerLoader\n", 1, "n1"),
            ("nodes:\n  - id: a\n    function: f1\n  - id: b\n    function: f2\n    depends_on: [a]\n", 2, "a"),
            ("pipeline:\n  name: complex\nnodes:\n  - id: n1\n    function: Loader\n    config:\n      val: 10\n", 1, "n1"),
        ],
    )
    def test_happy_path_yaml(self, tmp_path, content, expected_node_count, expected_first_id):
        f = tmp_path / "valid.yaml"
        f.write_text(content, encoding="utf-8")

        schema = validate_yaml_config(str(f))
        assert len(schema.nodes) == expected_node_count
        assert schema.nodes[0].id == expected_first_id

    @pytest.mark.parametrize(
        "invalid_content, error_match",
        [
            ("invalid: yaml: [", "YAML Syntax Error"),
            ("nodes: 'not_a_list'", "YAML Schema Validation Error"),
            ("nodes:\n  - function: MissingID\n", "YAML Schema Validation Error"),
        ],
    )
    def test_failure_scenarios_yaml(self, tmp_path, invalid_content, error_match):
        f = tmp_path / "invalid.yaml"
        f.write_text(invalid_content, encoding="utf-8")

        with pytest.raises(InvalidPipelineError) as exc_info:
            validate_yaml_config(str(f))
        assert error_match in str(exc_info.value)

    def test_nonexistent_file_yaml(self):
        with pytest.raises(InvalidPipelineError) as exc_info:
            validate_yaml_config("/nonexistent/file/path.yaml")
        assert "does not exist" in str(exc_info.value)


# =============================================================================
# 2. TestGraphValidator
# =============================================================================
class TestGraphValidator:
    """Test suite for GraphValidator / pre_flight_check."""

    @pytest.mark.parametrize(
        "nodes",
        [
            [{"id": "n1", "function": "BrukerLoader", "depends_on": []}],
            [
                {"id": "n1", "function": "BrukerLoader", "depends_on": []},
                {"id": "n2", "function": "MotionCheck", "depends_on": ["n1"]},
            ],
            [
                {"id": "a", "function": "BrukerLoader", "depends_on": []},
                {"id": "b", "function": "MotionCheck", "depends_on": ["a"]},
                {"id": "c", "function": "DiffImage", "depends_on": ["a", "b"]},
            ],
        ],
    )
    def test_happy_path_graph(self, nodes):
        mock_reg = MagicMock()
        mock_reg.get.return_value = lambda payload: {"status": "ok"}

        res = pre_flight_check(nodes, registry_inst=mock_reg)
        assert res["valid"] is True
        assert res["nodes_checked"] == len(nodes)

    @pytest.mark.parametrize(
        "nodes, expected_error",
        [
            ([{"id": "n1", "function": "f"}, {"id": "n1", "function": "f"}], "Duplicate node ids"),
            ([{"id": "n1", "function": "f", "depends_on": ["missing"]}], "Unknown dependency"),
            ([{"id": "n1", "function": "f", "depends_on": ["n1"]}], "cannot depend on itself"),
        ],
    )
    def test_validation_errors(self, nodes, expected_error):
        with pytest.raises(InvalidPipelineError) as exc_info:
            validate_pipeline(nodes)
        assert expected_error in str(exc_info.value)

    def test_pre_flight_unregistered_function(self):
        nodes = [{"id": "n1", "function": "UnregisteredFunc"}]
        mock_reg = MagicMock()
        mock_reg.get.side_effect = KeyError("Not found")

        with pytest.raises(InvalidPipelineError) as exc_info:
            pre_flight_check(nodes, registry_inst=mock_reg)
        assert "not registered" in str(exc_info.value)


# =============================================================================
# 3. TestPipelineExecutionEngine
# =============================================================================
class TestPipelineExecutionEngine:
    """Test suite for Pipeline execution engine."""

    def test_pipeline_execution_happy_path(self):
        pl = Pipeline(name="test_pl")
        n1 = Node(node_id="n1", function_name="func1", config={"param": 1})
        n2 = Node(node_id="n2", function_name="func2", depends_on=["n1"])
        pl.add_node(n1)
        pl.add_node(n2)

        def mock_exec_1(inputs):
            return {"status": "success", "data": [1, 2, 3]}

        def mock_exec_2(inputs):
            return {"status": "success", "result": 42}

        n1.execute = mock_exec_1
        n2.execute = mock_exec_2

        results = pl.execute()
        assert n1.status == NodeStatus.COMPLETED
        assert n2.status == NodeStatus.COMPLETED
        assert len(results) == 2

    def test_pipeline_execution_node_failure(self):
        pl = Pipeline(name="failing_pl", stop_on_failure=True)
        n1 = Node(node_id="n1", function_name="failing_func")
        n2 = Node(node_id="n2", function_name="subsequent_func", depends_on=["n1"])
        pl.add_node(n1)
        pl.add_node(n2)

        def mock_fail(inputs):
            raise RuntimeError("Hardware Error")

        n1.execute = mock_fail

        results = pl.execute()
        assert n1.status == NodeStatus.FAILED
        assert n2.status == NodeStatus.PENDING

    def test_topological_order_execution(self):
        pl = Pipeline(name="topo_pl")
        execution_order = []

        def make_exec(name):
            def _exec(inputs):
                execution_order.append(name)
                return {"status": "success"}
            return _exec

        n1 = Node(node_id="B", function_name="func", depends_on=["A"])
        n2 = Node(node_id="A", function_name="func", depends_on=[])
        pl.add_node(n1)
        pl.add_node(n2)

        n1.execute = make_exec("B")
        n2.execute = make_exec("A")

        pl.execute()
        assert execution_order == ["A", "B"]


# =============================================================================
# 4. TestCacheManager
# =============================================================================
class TestCacheManager:
    """Test suite for CacheManager."""

    def test_hash_computation(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "f1.txt").write_text("hello")

        cfg = tmp_path / "cfg.yaml"
        cfg.write_text("nodes: []")

        hash1 = CacheManager.compute_hash(str(data_dir), str(cfg))
        hash2 = CacheManager.compute_hash(str(data_dir), str(cfg))
        assert hash1 == hash2

        # Change config content -> hash must change
        cfg.write_text("nodes: [{id: a}]")
        hash3 = CacheManager.compute_hash(str(data_dir), str(cfg))
        assert hash1 != hash3

    def test_store_and_get_cached_result(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cm = CacheManager(str(cache_dir))

        data_dir = str(tmp_path / "d")
        cfg_path = str(tmp_path / "c.yaml")
        os.makedirs(data_dir, exist_ok=True)
        with open(cfg_path, "w") as f:
            f.write("content")

        res_payload = {"status": "COMPLETED", "cbf": 55.4}
        key = cm.store_result(data_dir, cfg_path, res_payload)

        assert cm.is_cached(data_dir, cfg_path) is True
        cached = cm.get_cached_result(data_dir, cfg_path)
        assert cached == res_payload

    def test_clear_cache(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cm = CacheManager(str(cache_dir))

        data_dir = str(tmp_path / "d")
        cfg_path = str(tmp_path / "c.yaml")
        os.makedirs(data_dir, exist_ok=True)
        with open(cfg_path, "w") as f:
            f.write("content")

        cm.store_result(data_dir, cfg_path, {"status": "ok"})
        assert len(cm.list_entries()) == 1

        cm.clear_cache()
        assert len(cm.list_entries()) == 0
        assert cm.is_cached(data_dir, cfg_path) is False


# =============================================================================
# 5. TestReportGenerator
# =============================================================================
class TestReportGenerator:
    """Test suite for ReportGenerator / generate_report."""

    def test_generate_report_outputs(self, tmp_path):
        results = [
            BatchResult(job_id="j1", status=BatchStatus.COMPLETED, data_dir="/data/1", config_path="cfg.yaml", start_time=100.0, end_time=102.5, result={"res": 1}),
            BatchResult(job_id="j2", status=BatchStatus.FAILED, data_dir="/data/2", config_path="cfg.yaml", start_time=100.0, end_time=101.0, result=None, error="Crash Error"),
        ]

        out_dir = str(tmp_path / "reports")
        html_path, json_path = generate_report(results, out_dir, base_name="test_rep")

        assert os.path.exists(html_path)
        assert os.path.exists(json_path)

        # Check HTML content
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        assert "PyASL Batch Report" in html_content
        assert "j1" in html_content
        assert "j2" in html_content
        assert "Crash Error" in html_content

        # Check JSON content
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        assert json_data["summary"]["total"] == 2
        assert json_data["summary"]["completed"] == 1
        assert json_data["summary"]["failed"] == 1
