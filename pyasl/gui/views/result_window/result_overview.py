"""
gui/views/result_window/result_overview.py
--------------------------------------------
Dynamic metrics cards panel.

Auto-detects numerical/categorical fields and generates
appropriate summary cards from the actual processed data.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
        QScrollArea, QSizePolicy,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class MetricCard(QFrame):
    """Individual metric card widget."""

    def __init__(self, label: str, value: str, parent=None):
        super().__init__(parent)
        self.setObjectName("metric_card")
        self._setup_ui(label, value)

    def _setup_ui(self, label: str, value: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        layout.setSpacing(2)

        self._value_lbl = QLabel(str(value))
        self._value_lbl.setFont(QFont("Segoe UI", DesignTokens.FONT_SIZE_LG, QFont.Weight.Bold))
        self._value_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; background: transparent;")
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._value_lbl)

        self._label_lbl = QLabel(label)
        self._label_lbl.setFont(QFont("Segoe UI", DesignTokens.FONT_SIZE_XS))
        self._label_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; background: transparent;")
        self._label_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._label_lbl)

        self.setFixedHeight(64)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.setStyleSheet(f"""
            MetricCard {{
                background: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {DesignTokens.BORDER_RADIUS_MD}px;
            }}
        """)

    def update_value(self, value: str):
        self._value_lbl.setText(str(value))


class ResultOverview(QWidget):
    """
    Dynamic metric cards panel.

    Cards are generated from actual data — never hard-coded.
    Uses AnalyticsService.compute_summary().
    """

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._cards: list = []
        self._setup_ui()

    def _setup_ui(self):
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Spacing.SM)

    def refresh(self):
        """Regenerate cards from current data."""
        # Clear existing cards
        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        result = self._service.current_result
        if not result:
            return

        summary = self._service.get_summary()

        for label, value in summary.items():
            card = MetricCard(label, str(value))
            self._layout.addWidget(card)
            self._cards.append(card)

    def _apply_theme_styles(self):
        for card in self._cards:
            card.setStyleSheet(f"""
                MetricCard {{
                    background: {Colors.BG_ELEVATED};
                    border: 1px solid {Colors.BORDER_SUBTLE};
                    border-radius: {DesignTokens.BORDER_RADIUS_MD}px;
                }}
            """)
