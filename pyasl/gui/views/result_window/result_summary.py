"""
gui/views/result_window/result_summary.py
-------------------------------------------
Dynamic summary view that inspects the processed dataset
and generates meaningful metrics.  No hard-coded values.
"""
from __future__ import annotations

import logging
from typing import List

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QScrollArea, QFrame, QGridLayout, QSizePolicy,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class MetricCard(QFrame):
    """Small card showing a single metric label + value."""

    def __init__(self, label: str, value: str, icon: str = "", parent=None):
        super().__init__(parent)
        self.setAccessibleName(f"Metric: {label}")
        self._setup(label, value, icon)

    def _setup(self, label: str, value: str, icon: str):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"padding: {Spacing.SM}px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(2)

        lbl = QLabel(f"{icon} {label}".strip())
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: {DesignTokens.FONT_SIZE_SM}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(lbl)

        val = QLabel(value)
        val.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        val.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(val)


class FieldSummaryRow(QFrame):
    """One row in the per-field summary table."""

    def __init__(self, name: str, stats: dict, parent=None):
        super().__init__(parent)
        self.setAccessibleName(f"Field summary: {name}")
        self.setStyleSheet(
            f"QFrame {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: {Spacing.XS}px; }}"
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(Spacing.SM)

        name_label = QLabel(name)
        name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        layout.addWidget(name_label, 0, 0, 1, 4)

        col = 0
        for key, val in stats.items():
            key_lbl = QLabel(key)
            key_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            val_lbl = QLabel(str(val))
            val_lbl.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; "
                f"background: transparent; border: none;"
            )
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(key_lbl, 1 + col // 4, (col % 4) * 2)
            layout.addWidget(val_lbl, 1 + col // 4, (col % 4) * 2 + 1)
            col += 1


class ResultSummary(QWidget):
    """
    Generates a dynamic summary from the current ProcessedResult.

    Layout::

        ┌──────────────────────────────────────────┐
        │ Result Summary                            │
        ├──────────────────────────────────────────┤
        │ [TotalRecords] [NumFields] [Mean] [Max]  │
        ├──────────────────────────────────────────┤
        │ Per-Field Details                         │
        │  absCBF   min=12.3  max=190  mean=84.6   │
        │  ...                                      │
        └──────────────────────────────────────────┘
    """

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        self._content_layout.setSpacing(Spacing.MD)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)

        outer.addWidget(scroll)

        # Empty state
        self._empty_label = QLabel("No processed records available for this result.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 13px; padding: 40px;"
        )
        self._empty_label.hide()
        self._content_layout.addWidget(self._empty_label)

    def refresh(self):
        """Rebuild summary from current result data."""
        # Clear existing cards
        self._clear_layout()

        result = self._service.current_result
        if not result or not result.entries:
            self._empty_label.show()
            return
        self._empty_label.hide()

        entries = result.entries
        ui = self._service.current_ui_state
        # Apply search filter from UI state
        filtered = self._service.get_filtered_entries()

        # ── Title ──
        title = QLabel("Result Summary")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        self._content_layout.addWidget(title)

        # ── Overview metric cards ──
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(Spacing.SM)

        total = len(entries)
        filtered_count = len(filtered)
        cards_layout.addWidget(MetricCard("Total Datasets", f"{total:,}", "📦"))
        if filtered_count != total:
            cards_layout.addWidget(
                MetricCard("Filtered", f"{filtered_count:,}", "🔍")
            )

        # Compute aggregate stats across all numerical entries
        numerical_entries = [e for e in filtered if e.mean_val is not None]
        if numerical_entries:
            means = [e.mean_val for e in numerical_entries if e.mean_val is not None]
            overall_mean = sum(means) / len(means) if means else 0
            cards_layout.addWidget(
                MetricCard("Avg Mean", f"{overall_mean:.2f}", "📊")
            )

            all_mins = [e.min_val for e in numerical_entries if e.min_val is not None]
            all_maxs = [e.max_val for e in numerical_entries if e.max_val is not None]
            if all_mins:
                cards_layout.addWidget(
                    MetricCard("Global Min", f"{min(all_mins):.2f}", "⬇️")
                )
            if all_maxs:
                cards_layout.addWidget(
                    MetricCard("Global Max", f"{max(all_maxs):.2f}", "⬆️")
                )

        cards_layout.addStretch()
        cards_widget = QWidget()
        cards_widget.setLayout(cards_layout)
        self._content_layout.addWidget(cards_widget)

        # ── Per-field details ──
        if filtered:
            detail_title = QLabel("Per-Dataset Details")
            detail_title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
            detail_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
            self._content_layout.addWidget(detail_title)

            for entry in filtered:
                stats = {}
                if entry.shape:
                    stats["Shape"] = str(entry.shape)
                stats["Dtype"] = entry.dtype
                stats["Size"] = f"{entry.size:,}"
                if entry.min_val is not None:
                    stats["Min"] = f"{entry.min_val:.4g}"
                if entry.max_val is not None:
                    stats["Max"] = f"{entry.max_val:.4g}"
                if entry.mean_val is not None:
                    stats["Mean"] = f"{entry.mean_val:.4g}"
                if entry.std_val is not None:
                    stats["Std"] = f"{entry.std_val:.4g}"

                row = FieldSummaryRow(entry.name, stats)
                self._content_layout.addWidget(row)

        self._content_layout.addStretch()

    def _clear_layout(self):
        """Remove all widgets from the content layout."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._empty_label:
                widget.deleteLater()

    def _apply_theme_styles(self):
        self.setStyleSheet(f"background: {Colors.BG_PRIMARY};")
