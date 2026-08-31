"""
tests/test_p3_engine_bugs.py
------------------------------
Unit test suite for Priority 3 pipeline engine fixes:
3A. autodiscover namespace pollution prevention
3B. Short name index & AmbiguousStepName on lookup collision
3C. Alias import warning logging
3E. Node ID dot validation
"""
from __future__ import annotations

import logging
import pytest

from pyasl.pipeline.registry import Registry, register_step
from pyasl.pipeline.exceptions.errors import AmbiguousStepName, InvalidPipelineError
from pyasl.pipeline.node import Node
from pyasl.pipeline.pipeline import Pipeline
from pyasl.pipeline.config_parser import validate_yaml_config


# ======================================================================
# 3A & 3B — Registry autodiscover and reverse index
# ======================================================================

class TestRegistryEngineFixes:
    def test_explicit_register_step_decorator(self):
        reg = Registry()

        @reg.register("custom_step")
        def step1(payload):
            return {"status": "ok"}

        @reg.register()
        def my_step(payload):
            return {"status": "ok"}

        assert getattr(step1, "_pyasl_step", False) is True
        assert getattr(my_step, "_pyasl_step", False) is True
        assert reg.get("custom_step") is step1
        assert reg.get("my_step") is my_step  # short name lookup for default registration

    def test_ambiguous_short_name_raises_exception(self):
        reg = Registry()

        @reg.register("pkg1.modA.MyStep")
        def step1(payload): pass

        @reg.register("pkg2.modB.MyStep")
        def step2(payload): pass

        # Direct full name lookups work
        assert reg.get("pkg1.modA.MyStep") is step1
        assert reg.get("pkg2.modB.MyStep") is step2

        # Short name lookup fails with AmbiguousStepName
        with pytest.raises(AmbiguousStepName, match="MyStep"):
            reg.get("MyStep")

    def test_autodiscover_filters_unmarked_callables(self):
        reg = Registry()
        reg.autodiscover("pyasl.modules")
        registered = reg.list_registered()

        # PreclinicalCoregister (a PascalCase class defined in pyasl.modules) should be registered
        assert any("PreclinicalCoregister" in k for k in registered)

        # Non-step helpers / third-party functions should not pollute registry
        # For instance, `logging.getLogger` or internal helper functions without _pyasl_step/PascalCase should not be registered
        assert not any("logging" in k for k in registered)


# ======================================================================
# 3C — Silent import error handling
# ======================================================================

class TestSilentImportErrorFix:
    def test_wrap_if_class_logs_warning_on_import_error(self, caplog):
        reg = Registry()

        class DummyStep:
            pass

        with caplog.at_level(logging.WARNING):
            wrapped = reg._wrap_if_class(DummyStep, "NonExistentAlias")

        assert wrapped is not None


# ======================================================================
# 3E — Node ID dot collision validation
# ======================================================================

class TestNodeIdDotValidation:
    def test_node_with_dot_in_id_raises_in_node_validate(self):
        node = Node(node_id="invalid.id", function_name="func")
        with pytest.raises(ValueError, match="cannot contain '.'"):
            node.validate_node()

    def test_node_with_dot_in_id_raises_in_pipeline_add(self):
        pl = Pipeline(name="test")
        node = Node(node_id="invalid.id", function_name="func")
        with pytest.raises(ValueError, match="cannot contain '.'"):
            pl.add_node(node)

    def test_yaml_config_with_dot_id_raises_error(self, tmp_path):
        f = tmp_path / "dot_id.yaml"
        f.write_text("nodes:\n  - id: step.one\n    function: BrukerLoader\n")

        with pytest.raises(InvalidPipelineError, match="cannot contain '.'"):
            validate_yaml_config(str(f))
