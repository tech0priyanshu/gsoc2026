"""
tests/result_window/test_services.py
--------------------------------------
Unit tests for core services:
- ResultService
- AnalyticsService
- ResultValidator
- ResultRepository
- ExportService
"""
from __future__ import annotations

import os
import json
import pytest
import numpy as np

from pyasl.gui.models.result_data import (
    DatasetEntry, ProcessedResult, ResultMetadata, ComparisonPair
)
from pyasl.gui.models.result_ui_state import (
    ResultUIState, ViewMode, VisualizationType, FilterRule, FilterGroup, FilterOperator, FilterLogic, SortSpec, SortDirection
)
from pyasl.gui.services.analytics_service import AnalyticsService, ChartData
from pyasl.gui.services.result_validator import ResultValidator, ValidationIssue
from pyasl.gui.services.result_repository import ResultRepository
from pyasl.gui.services.export_service import ResultExporter


# ---------------------------------------------------------------------------
# AnalyticsService Tests
# ---------------------------------------------------------------------------

class TestAnalyticsService:

    def test_compute_summary(self, sample_entries):
        analytics = AnalyticsService()
        summary = analytics.compute_summary(sample_entries)

        assert summary["Total Records"] == 5
        assert "Valid Arrays" in summary
        assert "Global Min" in summary
        assert "Global Max" in summary
        assert "Average Mean" in summary

    def test_compute_summary_empty(self):
        analytics = AnalyticsService()
        summary = analytics.compute_summary([])
        assert summary["Total Records"] == 0

    def test_search_entries(self, sample_entries):
        analytics = AnalyticsService()

        # Search for absCBF
        res = analytics.search_entries(sample_entries, "absCBF")
        assert len(res) == 1
        assert res[0].name == "absCBF"

        # Search case-insensitive
        res = analytics.search_entries(sample_entries, "brain")
        assert len(res) == 1
        assert res[0].name == "BrainMask"

        # Empty query
        res = analytics.search_entries(sample_entries, "")
        assert len(res) == 5

    def test_filter_entries(self, sample_entries):
        analytics = AnalyticsService()

        # Rule: mean_val > 50
        rule = FilterRule(field="mean_val", operator=FilterOperator.GREATER_THAN, value=50.0)
        group = FilterGroup(rules=[rule], logic=FilterLogic.AND)

        filtered = analytics.apply_filters(sample_entries, group)
        assert all(e.mean_val is not None and e.mean_val > 50.0 for e in filtered)

    def test_sort_entries(self, sample_entries):
        analytics = AnalyticsService()

        spec = SortSpec(field="mean_val", direction=SortDirection.ASC)
        sorted_entries = analytics.sort_entries(sample_entries, [spec])

        means = [e.mean_val for e in sorted_entries if e.mean_val is not None]
        assert means == sorted(means)

    def test_prepare_pie_data(self, sample_entries):
        analytics = AnalyticsService()
        data = analytics.prepare_pie_data(sample_entries, category_field="name", aggregation="count")

        assert data.is_valid
        assert data.chart_type == "pie"
        assert len(data.points) > 0

    def test_prepare_bar_data(self, sample_entries):
        analytics = AnalyticsService()
        data = analytics.prepare_bar_data(sample_entries, x_field="name", y_field="mean_val")

        assert data.is_valid
        assert data.chart_type == "bar"
        assert len(data.x_values) == len(data.y_values)


# ---------------------------------------------------------------------------
# ResultValidator Tests
# ---------------------------------------------------------------------------

class TestResultValidator:

    def test_validate_valid_result(self, sample_result):
        validator = ResultValidator()
        res = validator.validate(sample_result)
        assert res.is_valid

    def test_validate_empty_result(self, empty_result):
        validator = ResultValidator()
        res = validator.validate(empty_result)
        # Empty result should report warning or error depending on validator rules
        assert not res.is_valid or len(res.issues) > 0


# ---------------------------------------------------------------------------
# ResultRepository Tests
# ---------------------------------------------------------------------------

class TestResultRepository:

    def test_save_and_load(self, tmp_results_dir, sample_result):
        repo = ResultRepository(tmp_results_dir)
        ui_state = ResultUIState(active_view=ViewMode.SUMMARY)

        res_id = repo.save(sample_result, ui_state)
        assert res_id == sample_result.result_id

        # Load back
        loaded_res = repo.load(res_id)
        assert loaded_res is not None
        assert loaded_res.name == sample_result.name
        assert len(loaded_res.entries) == len(sample_result.entries)

        loaded_ui = repo.load_ui_state(res_id)
        assert loaded_ui is not None
        assert loaded_ui.active_view == ViewMode.SUMMARY

    def test_list_all(self, tmp_results_dir, sample_result):
        repo = ResultRepository(tmp_results_dir)
        repo.save(sample_result)

        summaries = repo.list_all()
        assert len(summaries) == 1
        assert summaries[0].result_id == sample_result.result_id

    def test_delete(self, tmp_results_dir, sample_result):
        repo = ResultRepository(tmp_results_dir)
        res_id = repo.save(sample_result)

        assert repo.delete(res_id)
        assert repo.load(res_id) is None


# ---------------------------------------------------------------------------
# ResultService Integration Tests
# ---------------------------------------------------------------------------

class TestResultService:

    def test_filtered_entries(self, loaded_service):
        service = loaded_service

        # Set search query
        service.current_ui_state.search_query = "absCBF"
        entries = service.get_filtered_entries()
        assert len(entries) == 1
        assert entries[0].name == "absCBF"

    def test_save_and_load_workflow(self, loaded_service):
        service = loaded_service
        saved_id = service.save_result()
        assert saved_id is not None

        loaded = service.load_result(saved_id)
        assert loaded is not None
        assert loaded.result_id == saved_id


# ---------------------------------------------------------------------------
# ExportService Tests
# ---------------------------------------------------------------------------

class TestExportService:

    def test_export_csv(self, tmp_path, sample_result):
        exporter = ResultExporter()
        csv_path = str(tmp_path / "export.csv")

        exporter.export_full_result(sample_result, csv_path, fmt="csv")
        assert os.path.exists(csv_path)
        assert os.path.getsize(csv_path) > 0

    def test_export_json(self, tmp_path, sample_result):
        exporter = ResultExporter()
        json_path = str(tmp_path / "export.json")

        exporter.export_full_result(sample_result, json_path, fmt="json")
        assert os.path.exists(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["result_id"] == sample_result.result_id
