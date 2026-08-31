"""
gui/views/components/execution_summary_panel.py
-------------------------------------------------
Right-column execution summary panel for the monitor view.
Shows Total / Running / Completed / Failed / Duration stat rows
and a QPainter-drawn circular progress ring showing success rate.

Public API
----------
update_stats(total, completed, failed, duration)
refresh_theme()
"""
from __future__ import annotations

import math
from typing import List, Tuple

try:
    from PyQt6.QtCore import Qt, QRectF  # type: ignore
    from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QConicalGradient  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import Colors


# ---------------------------------------------------------------------------
# Progress Ring
# ---------------------------------------------------------------------------

class _ProgressRing(QWidget):
    """
    A minimal flat circular progress ring drawn with QPainter.
    Shows percentage text in the center.
    """

    _RING_WIDTH = 10
    _SIZE = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pct: float = 0.0
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_percentage(self, pct: float) -> None:
        """pct: 0.0 – 100.0"""
        self._pct = max(0.0, min(100.0, pct))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        rw = self._RING_WIDTH
        margin = rw // 2 + 2
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)

        # Track circle (background ring)
        p.setPen(QPen(QColor("#E5E7EB"), rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # Filled arc
        if self._pct > 0:
            span = int(self._pct / 100.0 * 360 * 16)
            pen_color = QColor("#22C55E") if self._pct >= 100 else (
                QColor("#F59E0B") if self._pct < 50 else QColor("#3B82F6")
            )
            p.setPen(QPen(pen_color, rw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            # Qt drawArc starts at 3 o'clock, goes counter-clockwise; we start at 12 o'clock
            p.drawArc(rect, 90 * 16, -span)

        # Center text
        pct_font = QFont("Inter", 15, QFont.Weight.Bold)
        p.setFont(pct_font)
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.drawText(
            QRectF(0, 0, w, h),
            Qt.AlignmentFlag.AlignCenter,
            f"{int(self._pct)}%",
        )
        p.end()


# ---------------------------------------------------------------------------
# Stat Row
# ---------------------------------------------------------------------------

class _StatRow(QWidget):
    """A single label : value row inside the summary panel."""

    def __init__(self, label: str, initial: str = "—", accent: str = "#94A3B8", parent=None):
        super().__init__(parent)
        self._accent = accent

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)

        # Dot indicator
        self._dot = QLabel("●")
        self._dot.setFixedWidth(12)
        self._dot.setStyleSheet(f"color: {accent}; font-size: 8px;")
        lay.addWidget(self._dot)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {Colors.TEXT_MUTED}; font-family: 'Inter', 'Segoe UI', sans-serif;"
        )
        lay.addWidget(self._lbl)
        lay.addStretch()

        self._val = QLabel(initial)
        self._val.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; font-family: 'Inter', 'Segoe UI', sans-serif;"
        )
        lay.addWidget(self._val)

    def set_value(self, v: str) -> None:
        self._val.setText(v)

    def refresh_theme(self) -> None:
        self._lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 500; color: {Colors.TEXT_MUTED}; font-family: 'Inter', 'Segoe UI', sans-serif;"
        )
        self._val.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; font-family: 'Inter', 'Segoe UI', sans-serif;"
        )


# ---------------------------------------------------------------------------
# Divider
# ---------------------------------------------------------------------------

class _HDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background-color: {Colors.BORDER}; border: none;")


# ---------------------------------------------------------------------------
# Main Panel
# ---------------------------------------------------------------------------

class ExecutionSummaryPanel(QWidget):
    """
    Right-column execution summary panel.

    Public API (called by MonitorPanelView._refresh_summary):
        update_stats(total, completed, failed, duration)
        refresh_theme()
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        # Section Title
        title_lbl = QLabel("Execution Summary")
        title_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"font-family: 'Inter', 'Segoe UI', sans-serif; margin-bottom: 12px;"
        )
        root.addWidget(title_lbl)
        root.addSpacing(12)

        # Stat rows
        self._rows: List[Tuple[str, _StatRow]] = []
        row_defs = [
            ("total",     "Total Nodes",  "—",    "#6366F1"),
            ("running",   "Running",      "—",    "#F59E0B"),
            ("completed", "Completed",    "—",    "#22C55E"),
            ("failed",    "Failed",       "—",    "#EF4444"),
            ("duration",  "Duration",     "0.0s", "#94A3B8"),
        ]
        for i, (key, label, init, accent) in enumerate(row_defs):
            row = _StatRow(label, init, accent)
            self._rows.append((key, row))
            root.addWidget(row)
            if i < len(row_defs) - 1:
                root.addWidget(_HDivider())

        root.addSpacing(20)

        # Divider before ring
        root.addWidget(_HDivider())
        root.addSpacing(16)

        # Progress Ring + Success Rate label
        ring_section = QVBoxLayout()
        ring_section.setSpacing(8)
        ring_section.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        rate_lbl = QLabel("Success Rate")
        rate_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rate_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {Colors.TEXT_MUTED}; "
            f"letter-spacing: 0.5px; text-transform: uppercase; font-family: 'Inter', 'Segoe UI', sans-serif;"
        )

        self._ring = _ProgressRing()

        ring_row = QHBoxLayout()
        ring_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ring_row.addWidget(self._ring)

        ring_section.addWidget(rate_lbl)
        ring_section.addLayout(ring_row)

        root.addLayout(ring_section)
        root.addStretch()

        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_stats(
        self, total: int, completed: int, failed: int, duration: float
    ) -> None:
        running = sum(
            1 for _, row in self._rows
            if row is not None  # guard
        ) - total  # not meaningful here, computed from outside

        # Retrieve running count by looking at the value of the "running" row directly
        # The monitor_panel_view sets this via keyword args; we accept the positional API
        # and compute running ourselves: running = total - completed - failed
        running_count = max(0, total - completed - failed)

        for key, row in self._rows:
            if key == "total":
                row.set_value(str(total))
            elif key == "running":
                row.set_value(str(running_count))
            elif key == "completed":
                row.set_value(str(completed))
            elif key == "failed":
                row.set_value(str(failed))
            elif key == "duration":
                row.set_value(f"{duration:.1f}s")

        pct = (completed / total * 100.0) if total > 0 else 0.0
        self._ring.set_percentage(pct)

    def refresh_theme(self) -> None:
        self._apply_theme_styles()
        for _, row in self._rows:
            row.refresh_theme()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_theme_styles(self):
        self.setStyleSheet(
            f"ExecutionSummaryPanel {{ "
            f"  background-color: {Colors.BG_PANEL}; "
            f"  border: 1px solid {Colors.BORDER}; "
            f"  border-radius: 16px; "
            f"}}"
        )
