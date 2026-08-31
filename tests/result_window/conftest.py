"""
tests/result_window/conftest.py
---------------------------------
Shared fixtures for Result Window tests.

Provides factories for ProcessedResult, DatasetEntry, and
mock ResultService instances.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import pytest

from pyasl.gui.models.result_data import (
    DatasetEntry, ProcessedResult, ResultMetadata,
    ComparisonPair, ResultSummary,
)
from pyasl.gui.models.result_ui_state import ResultUIState
from pyasl.gui.services.result_service import ResultService


# ---------------------------------------------------------------------------
# DatasetEntry factories
# ---------------------------------------------------------------------------

def make_entry(
    name: str = "absCBF",
    shape: tuple = (128, 128, 20),
    dtype: str = "float64",
    min_val: float = 0.0,
    max_val: float = 200.0,
    mean_val: float = 80.5,
    std_val: float = 30.2,
    size: int = 327680,
    has_data: bool = True,
    **kwargs,
) -> DatasetEntry:
    """Create a DatasetEntry with realistic defaults."""
    return DatasetEntry(
        name=name,
        file_path=kwargs.get("file_path", f"/tmp/test/{name}.npy"),
        shape=shape,
        dtype=dtype,
        ndim=len(shape),
        min_val=min_val,
        max_val=max_val,
        mean_val=mean_val,
        std_val=std_val,
        size=size,
        description=f"Test entry for {name}",
        metadata=kwargs.get("metadata", {}),
        has_data=has_data,
        error=kwargs.get("error"),
    )


def make_entries(count: int = 5) -> List[DatasetEntry]:
    """Create a list of realistic DatasetEntries."""
    templates = [
        ("absCBF", (128, 128, 20), "float64", 0.0, 200.0, 80.5, 30.2, 327680),
        ("relCBF", (128, 128, 20), "float64", -10.0, 150.0, 45.3, 22.1, 327680),
        ("BrainMask", (128, 128, 20), "uint8", 0.0, 1.0, 0.45, 0.49, 327680),
        ("M0", (128, 128), "float64", 100.0, 5000.0, 2500.0, 800.0, 16384),
        ("ATT", (128, 128, 20), "float64", 500.0, 2500.0, 1200.0, 350.0, 327680),
        ("PLD", (128, 128, 20), "float64", 0.0, 3000.0, 1800.0, 400.0, 327680),
        ("T1blood", (1,), "float64", 1.65, 1.65, 1.65, 0.0, 1),
    ]
    entries = []
    for i in range(min(count, len(templates))):
        name, shape, dtype, mn, mx, mean, std, sz = templates[i]
        entries.append(make_entry(name, shape, dtype, mn, mx, mean, std, sz))
    return entries


# ---------------------------------------------------------------------------
# ProcessedResult factory
# ---------------------------------------------------------------------------

def make_result(
    entry_count: int = 5,
    name: str = "Test Result",
    with_comparisons: bool = False,
    with_errors: bool = False,
    with_warnings: bool = False,
) -> ProcessedResult:
    """Create a ProcessedResult with realistic data."""
    entries = make_entries(entry_count)
    meta = ResultMetadata(
        pipeline_name="test_pipeline",
        pipeline_type="dag",
        asl_library="PyASL",
        asl_version="2.2.0",
        processing_duration=12.5,
        config_path="/tmp/test/config.yaml",
        node_count=10,
        completed_nodes=10,
        failed_nodes=0,
    )

    if with_warnings:
        meta.warnings = ["Low signal in slice 15", "High variance detected"]

    if with_errors:
        meta.errors = ["Motion correction failed for subject 3"]

    comparisons = []
    if with_comparisons:
        comparisons = [
            ComparisonPair(
                field_name="absCBF",
                original_value="(128, 128)",
                processed_value="(128, 128, 20)",
                difference="Changed ↕",
                has_changed=True,
            ),
            ComparisonPair(
                field_name="BrainMask",
                original_value="(128, 128, 20)",
                processed_value="(128, 128, 20)",
                difference="No change",
                has_changed=False,
            ),
        ]

    return ProcessedResult(
        result_id=str(uuid.uuid4()),
        name=name,
        source_reference="/tmp/test/data",
        entries=entries,
        processing_metadata=meta,
        comparisons=comparisons,
        input_schema={"asl_type": "PCASL", "ld": 1.8, "pld": 1.8},
    )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_entry():
    """Single DatasetEntry."""
    return make_entry()


@pytest.fixture
def sample_entries():
    """Multiple DatasetEntries."""
    return make_entries(5)


@pytest.fixture
def sample_result():
    """A ProcessedResult with typical data."""
    return make_result()


@pytest.fixture
def sample_result_with_comparisons():
    """A ProcessedResult with comparison data."""
    return make_result(with_comparisons=True)


@pytest.fixture
def sample_result_with_errors():
    """A ProcessedResult with errors and warnings."""
    return make_result(with_errors=True, with_warnings=True)


@pytest.fixture
def empty_result():
    """An empty ProcessedResult with no entries."""
    return ProcessedResult(name="Empty Result")


@pytest.fixture
def tmp_results_dir(tmp_path):
    """Temporary results directory."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    return str(results_dir)


@pytest.fixture
def result_service(tmp_results_dir):
    """A ResultService with a temporary storage directory."""
    return ResultService(tmp_results_dir)


@pytest.fixture
def loaded_service(result_service, sample_result):
    """A ResultService with a loaded result."""
    result_service._current_result = sample_result
    result_service._current_ui_state = ResultUIState()
    return result_service


@pytest.fixture
def ui_state():
    """A fresh ResultUIState."""
    return ResultUIState()
