"""
gui/views/result_window/result_window.py
------------------------------------------
Main container widget for the Result Analytics Dashboard.

Composes all sub-components into a cohesive analytics workspace.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
        QStackedWidget, QScrollArea, QFrame, QSizePolicy,
        QMessageBox, QApplication,
    )
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing
from pyasl.gui.models.result_data import ProcessedResult
from pyasl.gui.models.result_ui_state import (
    ResultUIState, ViewMode, VisualizationType, DensityMode,
)
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ResultWindow(QWidget):
    """
    Production-grade Result Analytics Dashboard.

    Layout::

        ┌──────────────────────────────────────────┐
        │ ResultHeader (save/export/more)           │
        ├──────────────────────────────────────────┤
        │ ResultOverview (metric cards)             │
        ├──────────────────────────────────────────┤
        │ ResultToolbar (view/viz/filter/search)    │
        ├──────────────────────────────────────────┤
        │ ┌────────────────────┬──────────────────┐│
        │ │ ContentArea        │ RecordDetails     ││
        │ │ (table/summary/    │ (side panel)      ││
        │ │  chart/compare)    │                   ││
        │ └────────────────────┴──────────────────┘│
        ├──────────────────────────────────────────┤
        │ ProcessingDetails (collapsible)           │
        └──────────────────────────────────────────┘
    """

    result_changed = pyqtSignal()

    def __init__(self, result_service: ResultService, parent=None):
        super().__init__(parent)
        self._service = result_service
        self._setup_ui()
        self._wire_signals()
        self._update_empty_state()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        main_layout.setSpacing(Spacing.SM)

        # Import sub-components
        from pyasl.gui.views.result_window.result_header import ResultHeader
        from pyasl.gui.views.result_window.result_overview import ResultOverview
        from pyasl.gui.views.result_window.result_toolbar import ResultToolbar
        from pyasl.gui.views.result_window.result_table import ResultTable
        from pyasl.gui.views.result_window.result_summary import ResultSummary
        from pyasl.gui.views.result_window.result_charts import ResultCharts
        from pyasl.gui.views.result_window.comparison_view import ComparisonView
        from pyasl.gui.views.result_window.record_details import RecordDetails
        from pyasl.gui.views.result_window.processing_details import ProcessingDetails
        from pyasl.gui.views.result_window.filter_builder import FilterBuilder

        # ── Header ──
        self._header = ResultHeader(self._service)
        main_layout.addWidget(self._header)

        # ── Overview metrics ──
        self._overview = ResultOverview(self._service)
        main_layout.addWidget(self._overview)

        # ── Toolbar ──
        self._toolbar = ResultToolbar(self._service)
        main_layout.addWidget(self._toolbar)

        # ── Content area with optional side panel ──
        self._content_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Content stack (Table / Summary / Visualization / Compare)
        self._content_stack = QStackedWidget()

        self._table_view = ResultTable(self._service)
        self._summary_view = ResultSummary(self._service)
        self._charts_view = ResultCharts(self._service)
        self._compare_view = ComparisonView(self._service)

        self._content_stack.addWidget(self._table_view)     # 0
        self._content_stack.addWidget(self._summary_view)   # 1
        self._content_stack.addWidget(self._charts_view)    # 2
        self._content_stack.addWidget(self._compare_view)   # 3

        self._content_splitter.addWidget(self._content_stack)

        # Record details panel
        self._details = RecordDetails(self._service)
        self._details.hide()
        self._content_splitter.addWidget(self._details)

        self._content_splitter.setStretchFactor(0, 3)
        self._content_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._content_splitter, stretch=1)

        # ── Processing details (collapsible) ──
        self._proc_details = ProcessingDetails(self._service)
        main_layout.addWidget(self._proc_details)

        # ── Filter builder drawer (hidden by default) ──
        self._filter_builder = FilterBuilder(self._service)
        self._filter_builder.hide()

        # ── Empty state ──
        self._empty_widget = QWidget()
        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        from PyQt6.QtWidgets import QLabel
        from PyQt6.QtGui import QFont

        icon = QLabel("📊")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px; background: transparent;")
        empty_layout.addWidget(icon)

        title = QLabel("No Result Loaded")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        empty_layout.addWidget(title)

        subtitle = QLabel(
            "Run a pipeline or batch task to see results here.\n"
            "Or open a saved result from the history."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px;")
        subtitle.setWordWrap(True)
        empty_layout.addWidget(subtitle)

        self._empty_widget.hide()
        main_layout.addWidget(self._empty_widget)

        self._apply_theme_styles()

    def _wire_signals(self):
        """Connect sub-component signals."""
        # Toolbar → view switching
        self._toolbar.view_changed.connect(self._on_view_changed)
        self._toolbar.viz_changed.connect(self._on_viz_changed)
        self._toolbar.filter_requested.connect(self._toggle_filter_builder)
        self._toolbar.search_changed.connect(self._on_search_changed)
        self._toolbar.density_changed.connect(self._on_density_changed)

        # Header → save/export
        self._header.save_requested.connect(self._on_save)
        self._header.save_as_requested.connect(self._on_save_as)
        self._header.export_requested.connect(self._on_export)

        # Table → record selection
        self._table_view.record_selected.connect(self._on_record_selected)

        # Filter builder → filter applied
        self._filter_builder.filters_applied.connect(self._on_filters_applied)
        self._filter_builder.filters_cleared.connect(self._on_filters_cleared)

        # Details panel close
        self._details.close_requested.connect(self._close_details)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_result(self, result: ProcessedResult):
        """Load a new result into the dashboard."""
        self._service._current_result = result
        self._service._current_ui_state = ResultUIState()
        self._refresh_all()
        self._update_empty_state()

    def refresh(self):
        """Refresh all views with current data."""
        self._refresh_all()

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    def _on_view_changed(self, mode: str):
        ui = self._service.current_ui_state
        try:
            vm = ViewMode(mode)
        except ValueError:
            vm = ViewMode.TABLE

        ui.active_view = vm

        index_map = {
            ViewMode.TABLE: 0,
            ViewMode.SUMMARY: 1,
            ViewMode.VISUALIZATION: 2,
            ViewMode.COMPARE: 3,
        }
        self._content_stack.setCurrentIndex(index_map.get(vm, 0))
        self._refresh_active_view()

    def _on_viz_changed(self, viz_type: str):
        ui = self._service.current_ui_state
        try:
            ui.visualization_type = VisualizationType(viz_type)
        except ValueError:
            ui.visualization_type = VisualizationType.AUTO

        if ui.active_view == ViewMode.VISUALIZATION:
            self._charts_view.refresh()

    def _on_search_changed(self, query: str):
        ui = self._service.current_ui_state
        ui.search_query = query
        self._refresh_active_view()
        self._toolbar.update_filter_count()

    def _on_density_changed(self, density: str):
        ui = self._service.current_ui_state
        try:
            ui.density = DensityMode(density)
        except ValueError:
            pass
        self._table_view.set_density(ui.density)

    def _toggle_filter_builder(self):
        if self._filter_builder.isVisible():
            self._filter_builder.hide()
        else:
            self._filter_builder.show()
            self._filter_builder.raise_()

    def _on_filters_applied(self):
        self._refresh_active_view()
        self._overview.refresh()
        self._toolbar.update_filter_count()

    def _on_filters_cleared(self):
        self._service.current_ui_state.filters.clear()
        self._on_filters_applied()

    def _on_record_selected(self, entry_name: str):
        ui = self._service.current_ui_state
        ui.selected_record = entry_name
        ui.details_panel_open = True
        self._details.show_entry(entry_name)
        self._details.show()

    def _close_details(self):
        ui = self._service.current_ui_state
        ui.details_panel_open = False
        self._details.hide()

    # ------------------------------------------------------------------
    # Save / Export
    # ------------------------------------------------------------------

    def _on_save(self):
        result_id = self._service.save_result()
        if result_id:
            self._show_toast("Result saved successfully.")
        else:
            QMessageBox.warning(self, "Save Failed", "Could not save the result.")

    def _on_save_as(self, name: str):
        result_id = self._service.save_result_as(name)
        if result_id:
            self._show_toast(f"Result saved as '{name}'.")
        else:
            QMessageBox.warning(self, "Save Failed", "Could not save the result.")

    def _on_export(self, fmt: str, path: str, export_type: str):
        try:
            if export_type == "current":
                self._service.export_current_view(path, fmt)
            elif export_type == "full":
                self._service.export_full_result(path, fmt)
            elif export_type == "pdf":
                self._service.export_pdf(path)
            self._show_toast(f"Exported to {path}")
        except Exception as exc:
            QMessageBox.critical(
                self, "Export Error",
                f"Failed to export:\n{exc}\n\nCheck the file path and try again."
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_all(self):
        """Refresh all sub-components."""
        self._header.refresh()
        self._overview.refresh()
        self._toolbar.refresh()
        self._refresh_active_view()
        self._proc_details.refresh()

    def _refresh_active_view(self):
        """Refresh only the active content view."""
        ui = self._service.current_ui_state
        if ui.active_view == ViewMode.TABLE:
            self._table_view.refresh()
        elif ui.active_view == ViewMode.SUMMARY:
            self._summary_view.refresh()
        elif ui.active_view == ViewMode.VISUALIZATION:
            self._charts_view.refresh()
        elif ui.active_view == ViewMode.COMPARE:
            self._compare_view.refresh()

    def _update_empty_state(self):
        """Show/hide empty state based on data availability."""
        has_result = self._service.current_result is not None
        self._empty_widget.setVisible(not has_result)
        self._header.setVisible(has_result)
        self._overview.setVisible(has_result)
        self._toolbar.setVisible(has_result)
        self._content_splitter.setVisible(has_result)
        self._proc_details.setVisible(has_result)

    def _show_toast(self, message: str):
        """Show a brief non-blocking notification."""
        # Use status bar if available, otherwise brief tooltip
        parent_window = self.window()
        if hasattr(parent_window, "statusBar"):
            parent_window.statusBar().showMessage(message, 3000)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme_styles(self):
        """Apply/re-apply theme styles to all sub-components."""
        self.setStyleSheet(f"background: {Colors.BG_PRIMARY};")

        self._content_splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {Colors.BORDER}; width: 2px; }}"
        )

        # Propagate to sub-components
        for widget in (
            self._header, self._overview, self._toolbar,
            self._table_view, self._summary_view, self._charts_view,
            self._compare_view, self._details, self._proc_details,
            self._filter_builder,
        ):
            if hasattr(widget, "_apply_theme_styles"):
                widget._apply_theme_styles()
