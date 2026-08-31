"""
gui/views/result_window/comparison_view.py
---------------------------------------------
Original vs Processed comparison view.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QScrollArea, QFrame, QGridLayout, QSizePolicy,
        QHeaderView, QTableWidget, QTableWidgetItem,
    )
    from PyQt6.QtGui import QFont, QColor
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ComparisonView(QWidget):
    """
    Compare original input data vs processed output.

    Layout::

        ┌──────────────────────────────────────────────┐
        │ Original vs Processed Comparison              │
        ├──────────────┬──────────────┬────────────────┤
        │ Field        │ Input        │ Processed      │ Diff
        │ absCBF       │ (128,128)    │ (128,128,20)   │ Changed ↑
        │ ...          │              │                │
        └──────────────┴──────────────┴────────────────┘
    """

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        self._content_layout.setSpacing(Spacing.MD)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)

        layout.addWidget(scroll)

        # Empty state
        self._empty_label = QLabel(
            "No comparison data available.\n\n"
            "Both original input and processed output are needed for comparison."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 13px; padding: 40px;"
        )
        self._content_layout.addWidget(self._empty_label)

    def refresh(self):
        """Rebuild comparison from current result."""
        self._clear_layout()

        result = self._service.current_result
        if not result or not result.entries:
            self._empty_label.show()
            return

        self._empty_label.hide()

        # Title
        title = QLabel("Original vs Processed Comparison")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        self._content_layout.addWidget(title)

        subtitle = QLabel(
            "Comparing input parameters with processed output metrics."
        )
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px;")
        subtitle.setWordWrap(True)
        self._content_layout.addWidget(subtitle)

        # Build comparison table
        table = QTableWidget()
        table.setAccessibleName("Comparison table")
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Field", "Original Value", "Processed Value", "Difference"])

        # Style the table
        table.setStyleSheet(
            f"QTableWidget {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; gridline-color: {Colors.BORDER}; "
            f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; }}"
            f"QHeaderView::section {{ background: {Colors.BG_TERTIARY}; "
            f"color: {Colors.TEXT_SECONDARY}; border: 1px solid {Colors.BORDER}; "
            f"padding: 6px; font-weight: bold; font-size: 11px; }}"
        )
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Populate with comparison data
        entries = result.entries

        # Use stored comparison pairs if available, else generate from entries
        rows_data = []

        if result.comparisons:
            for comp in result.comparisons:
                diff_text = comp.difference or ("Changed ↕" if comp.has_changed else "No change")
                rows_data.append((
                    comp.field_name,
                    str(comp.original_value) if comp.original_value is not None else "—",
                    str(comp.processed_value) if comp.processed_value is not None else "—",
                    diff_text,
                ))
        else:
            # Generate comparison from entry data
            input_info = result.input_schema or {}
            for entry in entries:
                field_name = entry.name
                processed_shape = str(entry.shape) if entry.shape else "—"
                processed_mean = f"{entry.mean_val:.4g}" if entry.mean_val is not None else "—"

                original_val = "—"
                diff = "—"
                if isinstance(input_info, dict) and field_name in input_info:
                    orig = input_info[field_name]
                    original_val = str(orig)
                    diff = "No change" if original_val == processed_shape else "Changed ↕"

                rows_data.append((field_name, original_val, processed_shape, diff))

                if entry.mean_val is not None:
                    rows_data.append(
                        (f"  {field_name} (mean)", "—", processed_mean, "Computed")
                    )
                if entry.min_val is not None and entry.max_val is not None:
                    range_str = f"[{entry.min_val:.4g}, {entry.max_val:.4g}]"
                    rows_data.append(
                        (f"  {field_name} (range)", "—", range_str, "Computed")
                    )

        table.setRowCount(len(rows_data))
        for row_idx, (field, orig, proc, diff_text) in enumerate(rows_data):
            table.setItem(row_idx, 0, QTableWidgetItem(field))
            table.setItem(row_idx, 1, QTableWidgetItem(orig))
            table.setItem(row_idx, 2, QTableWidgetItem(proc))

            diff_item = QTableWidgetItem(diff_text)
            # Visual treatment for changes (not relying only on color)
            if "Changed" in diff_text:
                diff_item.setForeground(QColor(Colors.WARNING))
                diff_item.setText(f"⚡ {diff_text}")
            elif "Computed" in diff_text:
                diff_item.setForeground(QColor(Colors.INFO))
                diff_item.setText(f"🔧 {diff_text}")
            elif "No change" in diff_text:
                diff_item.setForeground(QColor(Colors.SUCCESS))
                diff_item.setText(f"✓ {diff_text}")
            table.setItem(row_idx, 3, diff_item)

        table.setMinimumHeight(min(400, 40 + len(rows_data) * 30))
        self._content_layout.addWidget(table)
        self._content_layout.addStretch()

    def _clear_layout(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._empty_label:
                widget.deleteLater()

    def _apply_theme_styles(self):
        self.setStyleSheet(f"background: {Colors.BG_PRIMARY};")
