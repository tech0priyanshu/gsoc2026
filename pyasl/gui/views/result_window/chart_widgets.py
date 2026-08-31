"""
gui/views/result_window/chart_widgets.py
------------------------------------------
Matplotlib-based chart widget implementations.

Each chart type is a standalone widget that embeds a matplotlib
FigureCanvas into a PyQt6 layout.  The factory function
``create_chart_widget`` maps VisualizationType → widget.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
except ImportError:
    raise ImportError("PyQt6 required.")

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ImportError:
    HAS_MPL = False

import numpy as np

from pyasl.gui.constants import Colors
from pyasl.gui.models.result_ui_state import VisualizationType
from pyasl.gui.services.analytics_service import ChartData, AnalyticsService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base chart widget
# ---------------------------------------------------------------------------

class BaseChartWidget(QWidget):
    """Base class wrapping a matplotlib FigureCanvas."""

    def __init__(self, chart_data: ChartData, parent=None):
        super().__init__(parent)
        if not HAS_MPL:
            raise ImportError("matplotlib required")

        self._data = chart_data
        self._figure = Figure(figsize=(8, 5), dpi=100)
        self._figure.patch.set_facecolor(Colors.BG_SECONDARY)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

        self._render()

    def _render(self):
        raise NotImplementedError

    def _style_axes(self, ax):
        """Apply consistent theme to axes."""
        ax.set_facecolor(Colors.BG_SECONDARY)
        ax.tick_params(colors=Colors.TEXT_MUTED, labelsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color(Colors.BORDER)
        ax.spines["left"].set_color(Colors.BORDER)
        if self._data.title:
            ax.set_title(self._data.title, color=Colors.TEXT_PRIMARY,
                         fontsize=12, fontweight="bold", pad=12)


# ---------------------------------------------------------------------------
# Chart implementations
# ---------------------------------------------------------------------------

class BarChartWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)
        self._style_axes(ax)

        # Support both points-based and x/y values-based data
        if self._data.points:
            labels = [p.label for p in self._data.points]
            values = [p.value for p in self._data.points]
            colors = [p.color or Colors.ACCENT_PRIMARY for p in self._data.points]
        elif self._data.x_values and self._data.y_values:
            labels = [str(x) for x in self._data.x_values]
            values = [float(y) for y in self._data.y_values]
            colors = [self.CHART_COLORS[i % len(self.CHART_COLORS)]
                      for i in range(len(labels))]
        else:
            return

        if not labels:
            return

        bars = ax.bar(range(len(labels)), values, color=colors, edgecolor="none")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_xlabel(self._data.x_label or "", color=Colors.TEXT_MUTED)
        ax.set_ylabel(self._data.y_label or "", color=Colors.TEXT_MUTED)

        # Value labels on bars
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{val:.2g}", ha="center", va="bottom",
                    fontsize=8, color=Colors.TEXT_SECONDARY)

        self._figure.tight_layout()
        self._canvas.draw()

    CHART_COLORS = AnalyticsService.CHART_COLORS if 'AnalyticsService' in dir() else [
        "#830085", "#FE565D", "#22c55e", "#3b82f6", "#f59e0b",
        "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16", "#f97316",
    ]


class PieChartWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)

        labels = [p.label for p in self._data.points]
        values = [p.value for p in self._data.points]
        colors = [p.color or Colors.ACCENT_PRIMARY for p in self._data.points]

        if not labels or all(v == 0 for v in values):
            ax.text(0.5, 0.5, "No data for pie chart",
                    ha="center", va="center", color=Colors.TEXT_MUTED)
            self._canvas.draw()
            return

        wedges, texts, autotexts = ax.pie(
            values, labels=labels, colors=colors,
            autopct="%1.1f%%", startangle=90,
            textprops={"fontsize": 9, "color": Colors.TEXT_PRIMARY},
        )

        for autotext in autotexts:
            autotext.set_fontsize(8)
            autotext.set_color(Colors.TEXT_PRIMARY)

        ax.set_title(self._data.title or "", color=Colors.TEXT_PRIMARY,
                     fontsize=12, fontweight="bold")

        self._figure.tight_layout()
        self._canvas.draw()


class DonutChartWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)

        labels = [p.label for p in self._data.points]
        values = [p.value for p in self._data.points]
        colors = [p.color or Colors.ACCENT_PRIMARY for p in self._data.points]

        if not labels or all(v == 0 for v in values):
            ax.text(0.5, 0.5, "No data for donut chart",
                    ha="center", va="center", color=Colors.TEXT_MUTED)
            self._canvas.draw()
            return

        wedges, texts, autotexts = ax.pie(
            values, labels=labels, colors=colors,
            autopct="%1.1f%%", startangle=90, pctdistance=0.82,
            wedgeprops={"width": 0.35},
            textprops={"fontsize": 9, "color": Colors.TEXT_PRIMARY},
        )

        ax.set_title(self._data.title or "", color=Colors.TEXT_PRIMARY,
                     fontsize=12, fontweight="bold")
        self._figure.tight_layout()
        self._canvas.draw()


class LineChartWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)
        self._style_axes(ax)

        if self._data.series:
            for i, (name, y_vals) in enumerate(self._data.series.items()):
                color = self._data.points[i].color if i < len(self._data.points) else None
                x_vals = list(range(len(y_vals)))
                ax.plot(x_vals, y_vals, label=name, color=color, linewidth=1.5)
            ax.legend(fontsize=8, framealpha=0.8)
        elif self._data.x_values and self._data.y_values:
            ax.plot(self._data.x_values, self._data.y_values,
                    color=Colors.ACCENT_PRIMARY, linewidth=1.5)

        ax.set_xlabel(self._data.x_label or "", color=Colors.TEXT_MUTED)
        ax.set_ylabel(self._data.y_label or "", color=Colors.TEXT_MUTED)
        self._figure.tight_layout()
        self._canvas.draw()


class AreaChartWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)
        self._style_axes(ax)

        if self._data.x_values and self._data.y_values:
            ax.fill_between(self._data.x_values, self._data.y_values,
                            alpha=0.3, color=Colors.ACCENT_PRIMARY)
            ax.plot(self._data.x_values, self._data.y_values,
                    color=Colors.ACCENT_PRIMARY, linewidth=1.5)

        ax.set_xlabel(self._data.x_label or "", color=Colors.TEXT_MUTED)
        ax.set_ylabel(self._data.y_label or "", color=Colors.TEXT_MUTED)
        self._figure.tight_layout()
        self._canvas.draw()


class HistogramWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)
        self._style_axes(ax)

        if self._data.y_values:
            values = [v for v in self._data.y_values if v is not None]
            if values:
                bins = min(50, max(10, len(values) // 5))
                ax.hist(values, bins=bins, color=Colors.ACCENT_PRIMARY,
                        edgecolor=Colors.BG_PRIMARY, alpha=0.85)

        ax.set_xlabel(self._data.x_label or "Value", color=Colors.TEXT_MUTED)
        ax.set_ylabel(self._data.y_label or "Frequency", color=Colors.TEXT_MUTED)
        self._figure.tight_layout()
        self._canvas.draw()


class ScatterPlotWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)
        self._style_axes(ax)

        if self._data.x_values and self._data.y_values:
            ax.scatter(self._data.x_values, self._data.y_values,
                       c=Colors.ACCENT_PRIMARY, alpha=0.7, s=20, edgecolors="none")

        ax.set_xlabel(self._data.x_label or "", color=Colors.TEXT_MUTED)
        ax.set_ylabel(self._data.y_label or "", color=Colors.TEXT_MUTED)
        self._figure.tight_layout()
        self._canvas.draw()


class HeatmapWidget(BaseChartWidget):
    def _render(self):
        ax = self._figure.add_subplot(111)

        if self._data.matrix is not None and self._data.matrix.size > 0:
            im = ax.imshow(self._data.matrix, cmap="RdYlBu_r", aspect="auto")
            self._figure.colorbar(im, ax=ax, shrink=0.8)
            if self._data.categories:
                ax.set_xticks(range(len(self._data.categories)))
                ax.set_xticklabels(self._data.categories, rotation=45,
                                   ha="right", fontsize=8)
        else:
            ax.text(0.5, 0.5, "Insufficient data for heatmap",
                    ha="center", va="center", color=Colors.TEXT_MUTED,
                    transform=ax.transAxes)

        ax.set_title(self._data.title or "", color=Colors.TEXT_PRIMARY,
                     fontsize=12, fontweight="bold")
        self._figure.tight_layout()
        self._canvas.draw()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_CHART_MAP = {
    VisualizationType.BAR_CHART: BarChartWidget,
    VisualizationType.GROUPED_BAR: BarChartWidget,
    VisualizationType.STACKED_BAR: BarChartWidget,
    VisualizationType.PIE_CHART: PieChartWidget,
    VisualizationType.DONUT_CHART: DonutChartWidget,
    VisualizationType.LINE_CHART: LineChartWidget,
    VisualizationType.AREA_CHART: AreaChartWidget,
    VisualizationType.HISTOGRAM: HistogramWidget,
    VisualizationType.SCATTER_PLOT: ScatterPlotWidget,
    VisualizationType.HEATMAP: HeatmapWidget,
}


def create_chart_widget(
    chart_data: ChartData,
    viz_type: VisualizationType,
    parent: Optional[QWidget] = None,
) -> Optional[QWidget]:
    """Factory: returns the right chart widget for the requested type."""
    cls = _CHART_MAP.get(viz_type)
    if cls is None:
        return None
    return cls(chart_data, parent)
