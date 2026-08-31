"""
gui/views/result_window/result_charts.py
------------------------------------------
Chart container that renders matplotlib-based visualizations
using the extensible chart widget system.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QScrollArea, QFrame, QSizePolicy, QStackedWidget,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.models.result_ui_state import VisualizationType
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ResultCharts(QWidget):
    """
    Chart container that:
      - Reads the current VisualizationType from UI state
      - Calls AnalyticsService to prepare chart data
      - Renders the chart via matplotlib embedded widgets
      - Shows chart configuration controls via progressive disclosure
    """

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._current_chart_widget = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        self._content_layout.setSpacing(Spacing.MD)
        scroll.setWidget(content)

        layout.addWidget(scroll)

        # Chart config panel (progressive disclosure)
        from pyasl.gui.views.result_window.chart_configuration import ChartConfiguration
        self._chart_config = ChartConfiguration(self._service)
        self._chart_config.config_changed.connect(self._on_config_changed)
        self._content_layout.addWidget(self._chart_config)

        # Chart render area
        self._chart_frame = QFrame()
        self._chart_frame.setMinimumHeight(320)
        self._chart_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        self._chart_frame.setStyleSheet(
            f"QFrame {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; }}"
        )
        self._chart_layout = QVBoxLayout(self._chart_frame)
        self._chart_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        self._content_layout.addWidget(self._chart_frame, stretch=1)

        # Error / empty state
        self._message_label = QLabel()
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 13px; padding: 40px;"
        )
        self._message_label.hide()
        self._chart_layout.addWidget(self._message_label)

    def refresh(self):
        """Rebuild chart from current UI state + analytics."""
        result = self._service.current_result
        if not result or not result.entries:
            self._show_message("No processed data available for visualization.")
            return

        ui = self._service.current_ui_state
        viz_type = ui.visualization_type

        # Update config panel for current chart type
        self._chart_config.update_for_type(viz_type)

        # Auto-detect best viz
        if viz_type == VisualizationType.AUTO:
            viz_type = self._auto_detect_viz()

        # Get chart data from analytics service
        entries = self._service.get_filtered_entries()
        if not entries:
            self._show_message(
                "No data matches the current filters.\n\n"
                "Clear filters to see visualizations."
            )
            return

        try:
            chart_data = self._service.get_chart_data()

            if not chart_data.is_valid:
                self._show_message(chart_data.error_message or
                                   "This visualization is not available for the current data.")
                return

            self._render_chart(chart_data, viz_type)

        except Exception as exc:
            logger.exception("Chart rendering failed")
            self._show_message(
                f"Could not render chart: {exc}\n\n"
                f"Try a different visualization or check data fields."
            )

    def _auto_detect_viz(self) -> VisualizationType:
        """Inspect dataset schema and pick a sensible default chart."""
        entries = self._service.get_filtered_entries()
        if not entries:
            return VisualizationType.BAR_CHART

        numerical = [e for e in entries if e.mean_val is not None]
        if len(numerical) >= 2:
            # Multiple numerical datasets → bar chart comparing means
            return VisualizationType.BAR_CHART
        elif len(numerical) == 1:
            return VisualizationType.HISTOGRAM
        else:
            return VisualizationType.BAR_CHART

    def _render_chart(self, chart_data, viz_type: VisualizationType):
        """Render chart_data using matplotlib."""
        self._clear_chart()
        self._message_label.hide()

        try:
            from pyasl.gui.views.result_window.chart_widgets import create_chart_widget
            widget = create_chart_widget(chart_data, viz_type, self)
            if widget:
                self._current_chart_widget = widget
                self._chart_layout.addWidget(widget)
            else:
                self._show_message("Chart type not supported yet.")
        except ImportError:
            self._show_message(
                "matplotlib is required for chart rendering.\n\n"
                "Install it with: pip install matplotlib"
            )
        except Exception as exc:
            logger.exception("Chart widget creation failed")
            self._show_message(f"Chart rendering error: {exc}")

    def _on_config_changed(self):
        """Re-render chart when config changes."""
        self.refresh()

    def _show_message(self, text: str):
        self._clear_chart()
        self._message_label.setText(text)
        self._message_label.show()

    def _clear_chart(self):
        if self._current_chart_widget:
            self._current_chart_widget.deleteLater()
            self._current_chart_widget = None
        self._message_label.hide()

    def _apply_theme_styles(self):
        self._chart_frame.setStyleSheet(
            f"QFrame {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; }}"
        )
