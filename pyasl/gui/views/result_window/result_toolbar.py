"""
gui/views/result_window/result_toolbar.py
-------------------------------------------
Toolbar with view selector, visualization selector,
filter button, search bar, and density toggle.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtWidgets import (
        QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton,
        QLineEdit, QSizePolicy,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.models.result_ui_state import ViewMode, VisualizationType, DensityMode
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ResultToolbar(QWidget):
    """
    Unified toolbar for the Result Window.

    View [Table ▼]   Visualization [Auto ▼]   [Filter 0]   🔍 Search...   [Density ▼]
    """

    view_changed = pyqtSignal(str)
    viz_changed = pyqtSignal(str)
    filter_requested = pyqtSignal()
    search_changed = pyqtSignal(str)
    density_changed = pyqtSignal(str)

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)  # 300ms debounce
        self._search_timer.timeout.connect(self._emit_search)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(Spacing.MD)

        # ── View selector ──
        view_label = QLabel("View")
        view_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; background: transparent; font-size: {DesignTokens.FONT_SIZE_SM}px;")
        layout.addWidget(view_label)

        self._view_combo = QComboBox()
        self._view_combo.setObjectName("result_view_selector")
        self._view_combo.setAccessibleName("View mode selector")
        self._view_combo.addItem("Table", ViewMode.TABLE.value)
        self._view_combo.addItem("Summary", ViewMode.SUMMARY.value)
        self._view_combo.addItem("Visualization", ViewMode.VISUALIZATION.value)
        self._view_combo.addItem("Compare", ViewMode.COMPARE.value)
        self._view_combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._view_combo.currentIndexChanged.connect(self._on_view_select)
        layout.addWidget(self._view_combo)

        # ── Visualization selector ──
        viz_label = QLabel("Visualization")
        viz_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; background: transparent; font-size: {DesignTokens.FONT_SIZE_SM}px;")
        layout.addWidget(viz_label)

        self._viz_combo = QComboBox()
        self._viz_combo.setObjectName("result_viz_selector")
        self._viz_combo.setAccessibleName("Visualization type selector")
        viz_items = [
            ("Auto", VisualizationType.AUTO.value),
            ("Bar Chart", VisualizationType.BAR_CHART.value),
            ("Pie Chart", VisualizationType.PIE_CHART.value),
            ("Donut Chart", VisualizationType.DONUT_CHART.value),
            ("Line Chart", VisualizationType.LINE_CHART.value),
            ("Area Chart", VisualizationType.AREA_CHART.value),
            ("Histogram", VisualizationType.HISTOGRAM.value),
            ("Scatter Plot", VisualizationType.SCATTER_PLOT.value),
            ("Grouped Bar", VisualizationType.GROUPED_BAR.value),
            ("Stacked Bar", VisualizationType.STACKED_BAR.value),
            ("Heatmap", VisualizationType.HEATMAP.value),
        ]
        for display, value in viz_items:
            self._viz_combo.addItem(display, value)
        self._viz_combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._viz_combo.currentIndexChanged.connect(self._on_viz_select)
        layout.addWidget(self._viz_combo)

        layout.addStretch()

        # ── Filter button ──
        self._filter_btn = QPushButton("Filter")
        self._filter_btn.setObjectName("result_filter_btn")
        self._filter_btn.setAccessibleName("Open filter builder")
        self._filter_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._filter_btn.clicked.connect(self.filter_requested.emit)
        layout.addWidget(self._filter_btn)

        # ── Search bar ──
        self._search_input = QLineEdit()
        self._search_input.setObjectName("result_search_input")
        self._search_input.setAccessibleName("Search results")
        self._search_input.setPlaceholderText("🔍  Search results...")
        self._search_input.setFixedHeight(DesignTokens.TOOLBAR_INPUT_HEIGHT)
        self._search_input.setMinimumWidth(180)
        self._search_input.setMaximumWidth(300)
        self._search_input.textChanged.connect(self._on_search_text)
        self._search_input.setClearButtonEnabled(True)
        layout.addWidget(self._search_input)

        # ── Density toggle ──
        self._density_combo = QComboBox()
        self._density_combo.setObjectName("result_density_selector")
        self._density_combo.setAccessibleName("Table density selector")
        self._density_combo.addItem("Comfortable", DensityMode.COMFORTABLE.value)
        self._density_combo.addItem("Compact", DensityMode.COMPACT.value)
        self._density_combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._density_combo.currentIndexChanged.connect(self._on_density_select)
        layout.addWidget(self._density_combo)

        self._apply_theme_styles()

    def refresh(self):
        """Sync toolbar with current UI state."""
        ui = self._service.current_ui_state

        # View selector
        for i in range(self._view_combo.count()):
            if self._view_combo.itemData(i) == ui.active_view.value:
                self._view_combo.blockSignals(True)
                self._view_combo.setCurrentIndex(i)
                self._view_combo.blockSignals(False)
                break

        # Viz selector
        for i in range(self._viz_combo.count()):
            if self._viz_combo.itemData(i) == ui.visualization_type.value:
                self._viz_combo.blockSignals(True)
                self._viz_combo.setCurrentIndex(i)
                self._viz_combo.blockSignals(False)
                break

        # Search
        if self._search_input.text() != ui.search_query:
            self._search_input.blockSignals(True)
            self._search_input.setText(ui.search_query)
            self._search_input.blockSignals(False)

        self.update_filter_count()

    def update_filter_count(self):
        """Update filter button badge."""
        ui = self._service.current_ui_state
        count = ui.filters.count
        search_active = bool(ui.search_query)

        if count > 0:
            self._filter_btn.setText(f"Filter ({count})")
            self._filter_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.DARK_PURPLE};
                    color: white;
                    border-radius: {DesignTokens.BORDER_RADIUS_SM}px;
                    padding: 0 {DesignTokens.TOOLBAR_BTN_PADDING}px;
                    font-weight: bold;
                }}
            """)
        else:
            self._filter_btn.setText("Filter")
            self._filter_btn.setStyleSheet("")

    # Handlers

    def _on_view_select(self, index: int):
        value = self._view_combo.itemData(index)
        if value:
            self.view_changed.emit(value)

    def _on_viz_select(self, index: int):
        value = self._viz_combo.itemData(index)
        if value:
            self.viz_changed.emit(value)

    def _on_search_text(self, text: str):
        self._search_timer.start()

    def _emit_search(self):
        self.search_changed.emit(self._search_input.text())

    def _on_density_select(self, index: int):
        value = self._density_combo.itemData(index)
        if value:
            self.density_changed.emit(value)

    def _apply_theme_styles(self):
        self.setStyleSheet(f"""
            ResultToolbar {{
                background: {Colors.BG_PANEL};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {DesignTokens.BORDER_RADIUS_SM}px;
            }}
        """)
