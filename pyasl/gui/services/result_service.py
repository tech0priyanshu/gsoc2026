"""
gui/services/result_service.py
--------------------------------
Unified interface consumed by the Result Window dashboard.

Coordinates ASLProcessor, ResultRepository, ResultValidator,
AnalyticsService, and ExportService.

Pure Python — no Qt dependency.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pyasl.gui.models.result_data import DatasetEntry, ProcessedResult, ResultSummary
from pyasl.gui.models.result_ui_state import ResultUIState
from pyasl.gui.services.analytics_service import AnalyticsService, ChartData
from pyasl.gui.services.asl_processor import ASLProcessor
from pyasl.gui.services.export_service import ResultExporter
from pyasl.gui.services.result_repository import ResultRepository
from pyasl.gui.services.result_validator import ResultValidator, ValidationResult

logger = logging.getLogger(__name__)


class ResultService:
    """
    Single entry point for all result operations.

    The dashboard UI should call this service — never access
    ASLProcessor, Repository, etc. directly.
    """

    def __init__(self, results_dir: str) -> None:
        self._processor = ASLProcessor()
        self._validator = ResultValidator()
        self._repository = ResultRepository(results_dir)
        self._analytics = AnalyticsService()
        self._exporter = ResultExporter()

        # In-memory cache of the current result
        self._current_result: Optional[ProcessedResult] = None
        self._current_ui_state: ResultUIState = ResultUIState()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_result(self) -> Optional[ProcessedResult]:
        return self._current_result

    @property
    def current_ui_state(self) -> ResultUIState:
        return self._current_ui_state

    @property
    def analytics(self) -> AnalyticsService:
        return self._analytics

    @property
    def exporter(self) -> ResultExporter:
        return self._exporter

    @property
    def repository(self) -> ResultRepository:
        return self._repository

    # ------------------------------------------------------------------
    # Process new results
    # ------------------------------------------------------------------

    def process_pipeline_result(
        self,
        summary: str,
        result_dict: Optional[Dict[str, Any]] = None,
    ) -> ProcessedResult:
        """
        Process a pipeline execution result into a ProcessedResult.

        Does NOT trigger re-processing.  Normalises existing output.
        """
        result = self._processor.process_pipeline_result(summary, result_dict)
        validation = self._validator.validate(result)

        if not validation.is_valid:
            for issue in validation.issues:
                if issue.severity == "error":
                    logger.error("Validation: %s — %s", issue.field, issue.message)
                    result.processing_metadata.errors.append(issue.message)

        self._current_result = result
        self._current_ui_state = ResultUIState()
        return result

    def process_batch_result(
        self,
        results_list: List[Dict[str, Any]],
        data_dirs: Optional[List[str]] = None,
    ) -> ProcessedResult:
        """
        Process a batch execution result into a ProcessedResult.
        """
        result = self._processor.process_batch_result(results_list, data_dirs)
        validation = self._validator.validate(result)

        if not validation.is_valid:
            for issue in validation.issues:
                if issue.severity == "error":
                    result.processing_metadata.errors.append(issue.message)

        self._current_result = result
        self._current_ui_state = ResultUIState()
        return result

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_result(self, result_id: str) -> Optional[ProcessedResult]:
        """Get a result by ID (from memory or storage)."""
        if (
            self._current_result
            and self._current_result.result_id == result_id
        ):
            return self._current_result

        # Try loading from repository
        result = self._repository.load(result_id)
        if result:
            self._current_result = result
            ui = self._repository.load_ui_state(result_id)
            if ui:
                self._current_ui_state = ui
            else:
                self._current_ui_state = ResultUIState()
        return result

    def get_entries(self) -> List[DatasetEntry]:
        """Get all entries from the current result."""
        if not self._current_result:
            return []
        return list(self._current_result.entries)

    def get_filtered_entries(self) -> List[DatasetEntry]:
        """
        Get entries filtered, searched, and sorted by current UI state.

        This is the primary data source for the dashboard views.
        Never mutates the canonical result.
        """
        if not self._current_result:
            return []

        entries = list(self._current_result.entries)
        ui = self._current_ui_state

        # Apply filters
        if not ui.filters.is_empty:
            entries = self._analytics.apply_filters(entries, ui.filters)

        # Apply search
        if ui.search_query:
            entries = self._analytics.search_entries(entries, ui.search_query)

        # Apply sorting
        if ui.sorting:
            entries = self._analytics.sort_entries(entries, ui.sorting)

        return entries

    # ------------------------------------------------------------------
    # Summary & analytics
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """Compute summary metrics for the current (filtered) data."""
        entries = self.get_filtered_entries()
        return self._analytics.compute_summary(entries)

    def get_chart_data(self) -> ChartData:
        """
        Prepare chart data based on current visualization config.
        """
        from pyasl.gui.models.result_ui_state import VisualizationType

        entries = self.get_filtered_entries()
        ui = self._current_ui_state
        viz = ui.visualization_type
        config = ui.visualization_config

        if viz == VisualizationType.AUTO:
            recommended = self._analytics.auto_recommend_visualization(entries)
            viz = VisualizationType(recommended)

        if viz == VisualizationType.PIE_CHART or viz == VisualizationType.DONUT_CHART:
            return self._analytics.prepare_pie_data(
                entries,
                category_field=config.category_field or "name",
                measure_field=config.measure_field or "mean_val",
                aggregation=config.aggregation or "count",
                group_small=config.group_small_categories,
                threshold_pct=config.small_category_threshold,
            )
        elif viz in (
            VisualizationType.BAR_CHART,
            VisualizationType.GROUPED_BAR,
            VisualizationType.STACKED_BAR,
        ):
            return self._analytics.prepare_bar_data(
                entries,
                x_field=config.x_field or "name",
                y_field=config.y_field or "mean_val",
                group_field=config.group_field,
            )
        elif viz in (VisualizationType.LINE_CHART, VisualizationType.AREA_CHART):
            return self._analytics.prepare_line_data(
                entries,
                x_field=config.x_field or "name",
                y_field=config.y_field or "mean_val",
            )
        elif viz == VisualizationType.SCATTER_PLOT:
            return self._analytics.prepare_scatter_data(
                entries,
                x_field=config.x_field or "min_val",
                y_field=config.y_field or "max_val",
            )
        elif viz == VisualizationType.HISTOGRAM:
            return self._analytics.prepare_histogram_data(
                entries,
                field_name=config.measure_field or "mean_val",
            )
        elif viz == VisualizationType.HEATMAP:
            return self._analytics.prepare_heatmap_data(
                entries,
                row_field=config.row_field or "name",
                col_field=config.col_field or "dtype",
                value_field=config.value_field or "mean_val",
            )

        # Default
        return self._analytics.prepare_bar_data(entries)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_result(self) -> Optional[str]:
        """Save the current result and UI state."""
        if not self._current_result:
            return None

        validation = self._validator.validate_for_save(self._current_result)
        if not validation.is_valid:
            logger.error("Cannot save — validation failed.")
            return None

        return self._repository.save(
            self._current_result, self._current_ui_state
        )

    def save_result_as(self, new_name: str) -> Optional[str]:
        """Save a copy of the current result with a new name."""
        if not self._current_result:
            return None
        return self._repository.save_as(
            self._current_result, new_name, self._current_ui_state
        )

    def load_result(self, result_id: str) -> Optional[ProcessedResult]:
        """Load a saved result (no reprocessing)."""
        result = self._repository.load(result_id)
        if result:
            self._current_result = result

            # Reload arrays from disk if entries have file paths
            self._reload_entry_data(result)

            ui = self._repository.load_ui_state(result_id)
            self._current_ui_state = ui or ResultUIState()
        return result

    def delete_result(self, result_id: str) -> bool:
        """Delete a saved result."""
        return self._repository.delete(result_id)

    def list_results(self) -> List[ResultSummary]:
        """List all saved results."""
        return self._repository.list_all()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_current_view(self, path: str, fmt: str = "csv") -> None:
        """Export the current filtered view."""
        if not self._current_result:
            return
        entries = self.get_filtered_entries()
        self._exporter.export_current_view(
            self._current_result, entries, path, fmt
        )

    def export_full_result(self, path: str, fmt: str = "csv") -> None:
        """Export the complete canonical result."""
        if not self._current_result:
            return
        self._exporter.export_full_result(self._current_result, path, fmt)

    def export_pdf(
        self,
        path: str,
        chart_image_path: Optional[str] = None,
    ) -> None:
        """Export a PDF report."""
        if not self._current_result:
            return
        entries = self.get_filtered_entries()
        summary = self.get_summary()
        self._exporter.export_pdf_report(
            self._current_result, entries, path, summary, chart_image_path
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_current(self) -> ValidationResult:
        """Validate the current result."""
        if not self._current_result:
            vr = ValidationResult()
            vr.add_error("result", "No result loaded.")
            return vr
        return self._validator.validate(self._current_result)

    # ------------------------------------------------------------------
    # Field introspection
    # ------------------------------------------------------------------

    def get_available_fields(self) -> List[str]:
        """Available fields for filtering/charting."""
        entries = self.get_entries()
        return self._analytics.get_available_fields(entries)

    def get_numerical_fields(self) -> List[str]:
        entries = self.get_entries()
        return self._analytics.get_numerical_fields(entries)

    def get_categorical_fields(self) -> List[str]:
        entries = self.get_entries()
        return self._analytics.get_categorical_fields(entries)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reload_entry_data(self, result: ProcessedResult) -> None:
        """Reload raw numpy data from disk for entries that have file paths."""
        import numpy as np
        import os

        for entry in result.entries:
            if entry.file_path and os.path.isfile(entry.file_path):
                try:
                    arr = np.load(entry.file_path, allow_pickle=False)
                    entry.raw_data = arr
                    entry.has_data = True
                except Exception as exc:
                    logger.warning("Could not reload %s: %s", entry.file_path, exc)
                    entry.has_data = False
