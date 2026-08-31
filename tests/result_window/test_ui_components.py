"""
tests/result_window/test_ui_components.py
--------------------------------------------
UI unit and integration tests for Result Window components:
- ResultWindow container
- ResultHeader
- ResultOverview
- ResultToolbar
- ResultTable
- ResultSummary
- ResultCharts
- ComparisonView
- RecordDetails
- ProcessingDetails
- FilterBuilder
- SearchBar
- ExportMenu
- SaveControls
- ResultHistory
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from pyasl.gui.models.result_data import ProcessedResult
from pyasl.gui.models.result_ui_state import ViewMode, VisualizationType, DensityMode
from pyasl.gui.views.result_window.result_window import ResultWindow
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
from pyasl.gui.views.result_window.search_bar import SearchBar
from pyasl.gui.views.result_window.export_menu import ExportMenu
from pyasl.gui.views.result_window.save_controls import SaveControls
from pyasl.gui.views.result_window.result_history import ResultHistory


@pytest.fixture(scope="session")
def qapp():
    """Ensure QApplication instance exists for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ---------------------------------------------------------------------------
# ResultWindow Container Tests
# ---------------------------------------------------------------------------

class TestResultWindowUI:

    def test_result_window_init(self, qapp, loaded_service):
        rw = ResultWindow(loaded_service)
        assert rw is not None
        assert rw.isVisible() is False  # hidden initially until shown

    def test_result_window_set_result(self, qapp, loaded_service, sample_result):
        rw = ResultWindow(loaded_service)
        rw.set_result(sample_result)
        rw.show()

        assert rw._service.current_result == sample_result
        assert rw._empty_widget.isVisible() is False
        assert rw._header.isVisible() is True

    def test_result_window_view_mode_switching(self, qapp, loaded_service, sample_result):
        rw = ResultWindow(loaded_service)
        rw.set_result(sample_result)
        rw.show()

        # Switch to summary view
        rw._on_view_changed("summary")
        assert rw._service.current_ui_state.active_view == ViewMode.SUMMARY
        assert rw._content_stack.currentIndex() == 1

        # Switch to visualization view
        rw._on_view_changed("visualization")
        assert rw._service.current_ui_state.active_view == ViewMode.VISUALIZATION
        assert rw._content_stack.currentIndex() == 2

        # Switch to compare view
        rw._on_view_changed("compare")
        assert rw._service.current_ui_state.active_view == ViewMode.COMPARE
        assert rw._content_stack.currentIndex() == 3


# ---------------------------------------------------------------------------
# Sub-component Tests
# ---------------------------------------------------------------------------

class TestSubComponentsUI:

    def test_result_table_refresh(self, qapp, loaded_service):
        table = ResultTable(loaded_service)
        table.refresh()
        assert table._table.model().rowCount() == 5

    def test_result_overview_refresh(self, qapp, loaded_service):
        overview = ResultOverview(loaded_service)
        overview.show()
        overview.refresh()
        assert overview.isVisible()

    def test_result_summary_refresh(self, qapp, loaded_service):
        summary = ResultSummary(loaded_service)
        summary.refresh()
        assert summary._empty_label.isVisible() is False

    def test_record_details_show(self, qapp, loaded_service):
        details = RecordDetails(loaded_service)
        details.show_entry("absCBF")
        assert details._empty_label.isVisible() is False

    def test_filter_builder_toggle(self, qapp, loaded_service):
        fb = FilterBuilder(loaded_service)
        fb._add_rule()
        assert len(fb._rule_rows) == 1

        fb._clear_all()
        assert len(fb._rule_rows) == 0

    def test_search_bar_emit(self, qapp):
        sb = SearchBar()
        searched = []
        sb.search_changed.connect(lambda q: searched.append(q))

        sb._input.setText("test")
        sb._timer.timeout.emit()
        assert searched == ["test"]

    def test_result_history_dialog(self, qapp, loaded_service):
        rh = ResultHistory(loaded_service)
        rh.load_history()
        assert rh._table is not None
