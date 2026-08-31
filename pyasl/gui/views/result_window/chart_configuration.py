"""
gui/views/result_window/chart_configuration.py
-------------------------------------------------
Progressive-disclosure chart configuration panel.

Only shows controls relevant to the selected visualization type.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QWidget, QHBoxLayout, QVBoxLayout, QLabel,
        QComboBox, QCheckBox, QPushButton, QFrame, QSizePolicy,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.models.result_ui_state import VisualizationType
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ChartConfiguration(QWidget):
    """
    Dynamic chart configuration panel.

    Progressive disclosure:
      - Pie/Donut: Category, Measure, Aggregation
      - Bar:       X-Axis, Y-Axis, Group By
      - Line/Area: X-Axis, Y-Axis, Series
      - Scatter:   X-Axis, Y-Axis, Size, Group
      - Heatmap:   Rows, Columns, Value, Aggregation
      - Histogram: Field, Bins
    """

    config_changed = pyqtSignal()

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._combos = {}
        self._setup_ui()

    def _setup_ui(self):
        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(Spacing.XS, Spacing.XS, Spacing.XS, Spacing.XS)
        self._main_layout.setSpacing(Spacing.MD)

        self.setStyleSheet(
            f"background: {Colors.BG_TERTIARY}; border-radius: 4px; "
            f"padding: {Spacing.XS}px;"
        )

        # Config controls will be added dynamically
        self._info_label = QLabel("Select a visualization to configure.")
        self._info_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent;"
        )
        self._main_layout.addWidget(self._info_label)

        # Group-small toggle (for pie/donut)
        self._group_small = QCheckBox("Group small categories")
        self._group_small.setObjectName("group_small_checkbox")
        self._group_small.setAccessibleName("Group small categories together")
        self._group_small.setChecked(True)
        self._group_small.stateChanged.connect(self._on_config_change)
        self._group_small.hide()
        self._main_layout.addWidget(self._group_small)

        # Apply button
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setObjectName("chart_apply_btn")
        self._apply_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._apply_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: white; "
            f"border: none; border-radius: 4px; padding: 0 {Spacing.MD}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_SECONDARY}; }}"
        )
        self._apply_btn.clicked.connect(self._on_apply)
        self._apply_btn.hide()
        self._main_layout.addWidget(self._apply_btn)

        self._main_layout.addStretch()

    def update_for_type(self, viz_type: VisualizationType):
        """Rebuild config controls for the given visualization type."""
        # Clear old combos
        for combo in self._combos.values():
            combo.deleteLater()
        self._combos.clear()

        # Remove old labels (keep info, group_small, apply, stretch)
        while self._main_layout.count() > 0:
            item = self._main_layout.takeAt(0)
            w = item.widget()
            if w and w not in (self._info_label, self._group_small, self._apply_btn):
                w.deleteLater()

        self._group_small.hide()
        self._apply_btn.hide()

        # Get field names
        field_names = self._get_field_names()

        if viz_type == VisualizationType.AUTO:
            self._info_label.setText("Auto: visualization will be chosen automatically.")
            self._main_layout.addWidget(self._info_label)
            return

        self._info_label.hide()

        configs = self._get_config_spec(viz_type)
        for label_text, key in configs:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; "
                f"background: transparent;"
            )
            self._main_layout.addWidget(lbl)

            combo = QComboBox()
            combo.setObjectName(f"chart_config_{key}")
            combo.setAccessibleName(f"Chart {label_text}")
            combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
            combo.addItem("(select)", "")
            for fn in field_names:
                combo.addItem(fn, fn)
            combo.currentIndexChanged.connect(self._on_config_change)
            self._main_layout.addWidget(combo)
            self._combos[key] = combo

        # Aggregation combo for types that need it
        if viz_type in (
            VisualizationType.PIE_CHART, VisualizationType.DONUT_CHART,
            VisualizationType.HEATMAP,
        ):
            lbl = QLabel("Aggregation")
            lbl.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; "
                f"background: transparent;"
            )
            self._main_layout.addWidget(lbl)

            agg_combo = QComboBox()
            agg_combo.setObjectName("chart_config_aggregation")
            agg_combo.setAccessibleName("Aggregation method")
            agg_combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
            for agg_name in ("Count", "Sum", "Mean", "Min", "Max"):
                agg_combo.addItem(agg_name, agg_name.lower())
            agg_combo.currentIndexChanged.connect(self._on_config_change)
            self._main_layout.addWidget(agg_combo)
            self._combos["aggregation"] = agg_combo

        # Show group-small for pie/donut
        if viz_type in (VisualizationType.PIE_CHART, VisualizationType.DONUT_CHART):
            self._group_small.show()
            self._main_layout.addWidget(self._group_small)

        self._apply_btn.show()
        self._main_layout.addWidget(self._apply_btn)
        self._main_layout.addStretch()

    def _get_config_spec(self, viz_type: VisualizationType):
        """Return (label, key) pairs for the given viz type."""
        specs = {
            VisualizationType.PIE_CHART: [("Category", "category"), ("Measure", "measure")],
            VisualizationType.DONUT_CHART: [("Category", "category"), ("Measure", "measure")],
            VisualizationType.BAR_CHART: [("X-Axis", "x_axis"), ("Y-Axis", "y_axis")],
            VisualizationType.GROUPED_BAR: [("X-Axis", "x_axis"), ("Y-Axis", "y_axis"), ("Group By", "group_by")],
            VisualizationType.STACKED_BAR: [("X-Axis", "x_axis"), ("Y-Axis", "y_axis"), ("Group By", "group_by")],
            VisualizationType.LINE_CHART: [("X-Axis", "x_axis"), ("Y-Axis", "y_axis")],
            VisualizationType.AREA_CHART: [("X-Axis", "x_axis"), ("Y-Axis", "y_axis")],
            VisualizationType.HISTOGRAM: [("Field", "field")],
            VisualizationType.SCATTER_PLOT: [("X-Axis", "x_axis"), ("Y-Axis", "y_axis")],
            VisualizationType.HEATMAP: [("Rows", "rows"), ("Columns", "columns"), ("Value", "value")],
        }
        return specs.get(viz_type, [])

    def _get_field_names(self) -> list:
        """Get available field names from the current result."""
        result = self._service.current_result
        if not result or not result.entries:
            return []
        return [e.name for e in result.entries]

    def _on_config_change(self):
        """Update UI state with current config values."""
        config = {}
        for key, combo in self._combos.items():
            config[key] = combo.currentData()
        config["group_small"] = self._group_small.isChecked()
        self._service.current_ui_state.visualization_config = config

    def _on_apply(self):
        """Apply config and signal re-render."""
        self._on_config_change()
        self.config_changed.emit()

    def _apply_theme_styles(self):
        self.setStyleSheet(
            f"background: {Colors.BG_TERTIARY}; border-radius: 4px; "
            f"padding: {Spacing.XS}px;"
        )
