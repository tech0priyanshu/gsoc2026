"""
gui/views/components/summary_bar.py
-------------------------------------
Compact metric cards — icon · large value · small label.
Target height: ~100px per card.  Flat modern design, no gradients.

Public API (unchanged):
    update_stats(total, completed, failed, duration)
    refresh_theme()
"""
from __future__ import annotations

from typing import Dict, List, Tuple

try:
    from PyQt6.QtCore import Qt  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import Colors


class SummaryBar(QWidget):
    """Four compact metric cards for execution stats."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)

        # (key, icon_glyph, label_text, accent_color)
        card_defs: List[Tuple[str, str, str, str]] = [
            ("total",     "⚡", "Total Tasks",  "#6366F1"),
            ("completed", "✓",  "Completed",    "#22C55E"),
            ("failed",    "✕",  "Failed",       "#EF4444"),
            ("duration",  "⏱", "Duration",     "#F59E0B"),
        ]

        self._val_labels: Dict[str, QLabel] = {}
        self._cards: List[Tuple[QFrame, str, QLabel, str]] = []   # (card, key, val_lbl, accent)

        for key, icon, label_text, accent in card_defs:
            card, val_lbl = self._build_card(key, icon, label_text, accent)
            self._val_labels[key] = val_lbl
            self._cards.append((card, key, val_lbl, accent))
            self._layout.addWidget(card, stretch=1)

        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Card builder
    # ------------------------------------------------------------------

    def _build_card(
        self, key: str, icon: str, label_text: str, accent: str
    ) -> Tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName(f"metric_card_{key}")
        card.setFixedHeight(100)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Icon row
        icon_row = QHBoxLayout()
        icon_row.setContentsMargins(0, 0, 0, 0)
        icon_row.setSpacing(0)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"background-color: {accent}18; color: {accent}; "
            f"border-radius: 8px; font-size: 13px; font-weight: bold;"
        )
        icon_row.addWidget(icon_lbl)
        icon_row.addStretch()
        lay.addLayout(icon_row)

        # Value
        init_val = "0.0s" if key == "duration" else "0"
        val_lbl = QLabel(init_val)
        val_lbl.setStyleSheet(
            f"font-size: 28px; font-weight: 800; color: {Colors.TEXT_PRIMARY}; "
            f"font-family: 'Inter', 'Segoe UI', sans-serif; line-height: 1;"
        )
        lay.addWidget(val_lbl)

        # Label
        lbl = QLabel(label_text.upper())
        lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {Colors.TEXT_MUTED}; "
            f"letter-spacing: 0.6px; font-family: 'Inter', 'Segoe UI', sans-serif;"
        )
        lay.addWidget(lbl)

        return card, val_lbl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_stats(
        self, total: int, completed: int, failed: int, duration: float
    ) -> None:
        self._val_labels["total"].setText(str(total))
        self._val_labels["completed"].setText(str(completed))
        self._val_labels["failed"].setText(str(failed))
        self._val_labels["duration"].setText(f"{duration:.1f}s")

    def refresh_theme(self) -> None:
        """Re-apply styles after a theme change."""
        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_theme_styles(self) -> None:
        for card, key, val_lbl, accent in self._cards:
            card.setStyleSheet(
                f"QFrame#metric_card_{key} {{"
                f"  background-color: {Colors.BG_PANEL};"
                f"  border: 1px solid {Colors.BORDER};"
                f"  border-radius: 16px;"
                f"}}"
                f"QFrame#metric_card_{key}:hover {{"
                f"  border: 1px solid {accent};"
                f"}}"
            )
            val_lbl.setStyleSheet(
                f"font-size: 28px; font-weight: 800; color: {Colors.TEXT_PRIMARY}; "
                f"font-family: 'Inter', 'Segoe UI', sans-serif; line-height: 1;"
            )
