"""
gui/views/components/node_timeline.py
---------------------------------------
Horizontal timeline widget that paints per-node status bars.
Each node is a row; a coloured bar indicates its execution phase.

Public API (unchanged):
    add_event(node_id, status)
    clear()
"""
from __future__ import annotations

import time
from typing import Dict, List

try:
    from PyQt6.QtCore import Qt, QRectF  # type: ignore
    from PyQt6.QtGui import QPainter, QColor, QFont, QPen  # type: ignore
    from PyQt6.QtWidgets import QWidget  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import Colors, STATUS_COLORS


class NodeTimelineWidget(QWidget):
    """
    Horizontal scrollable timeline showing per-node status bars.
    Each node is a row; a coloured bar fills its duration.
    """

    _ROW_H = 48
    _LABEL_W = 180
    _BAR_CORNER = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events: List[Dict] = []
        self._node_order: List[str] = []
        self.setMinimumHeight(180)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_event(self, node_id: str, status: str) -> None:
        self._events.append({
            "node_id": node_id, "status": status, "t": time.time(),
        })
        if node_id not in self._node_order:
            self._node_order.append(node_id)
        # Dynamic height based on node count
        min_h = max(180, len(self._node_order) * self._ROW_H + 24)
        self.setMinimumHeight(min_h)
        self.update()

    def clear(self) -> None:
        self._events.clear()
        self._node_order.clear()
        self.setMinimumHeight(180)
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = self.rect()

        # Background fill — matches card background
        p.fillRect(rect, QColor(Colors.BG_PANEL if Colors.BG_PANEL != "#000000" else "#FFFFFF"))

        if not self._node_order:
            self._draw_empty_state(p, rect)
            return

        self._draw_rows(p, rect)

    def _draw_empty_state(self, p: QPainter, rect):
        """Illustrated empty state — chart emoji + headline + subtitle."""
        cx = rect.width() / 2.0
        cy = rect.height() / 2.0

        # Large chart icon
        icon_font = QFont("Segoe UI Emoji", 28)
        p.setFont(icon_font)
        p.setPen(QColor(Colors.TEXT_MUTED))
        p.drawText(
            QRectF(cx - 30, cy - 60, 60, 44),
            Qt.AlignmentFlag.AlignCenter,
            "📊",
        )

        # Main title
        title_font = QFont("Inter", 13, QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QColor(Colors.TEXT_PRIMARY))
        p.drawText(
            QRectF(cx - 180, cy - 6, 360, 26),
            Qt.AlignmentFlag.AlignCenter,
            "No execution data",
        )

        # Subtitle
        sub_font = QFont("Inter", 10)
        p.setFont(sub_font)
        p.setPen(QColor(Colors.TEXT_MUTED))
        p.drawText(
            QRectF(cx - 220, cy + 22, 440, 22),
            Qt.AlignmentFlag.AlignCenter,
            "Run a workflow to visualize execution.",
        )

    def _draw_rows(self, p: QPainter, rect):
        row_h = self._ROW_H
        label_w = self._LABEL_W
        bar_area_w = max(100, self.width() - label_w - 120)

        # Latest status per node
        latest: Dict[str, str] = {}
        for ev in self._events:
            latest[ev["node_id"]] = ev["status"]

        for i, nid in enumerate(self._node_order):
            y = i * row_h
            status = latest.get(nid, "PENDING")
            status_hex = STATUS_COLORS.get(status, Colors.TEXT_MUTED)
            color = QColor(status_hex)

            # Alternating row background
            if i % 2 == 1:
                alt_bg = QColor(Colors.BG_ELEVATED)
                alt_bg.setAlpha(80)
                p.fillRect(0, y, rect.width(), row_h, alt_bg)

            # Row bottom border
            p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
            p.drawLine(0, y + row_h - 1, rect.width(), y + row_h - 1)

            # Node Label
            label_font = QFont("Inter", 10, QFont.Weight.DemiBold)
            p.setFont(label_font)
            p.setPen(QColor(Colors.TEXT_PRIMARY))
            p.drawText(
                QRectF(14, y, label_w - 20, row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                nid[:26],
            )

            # Bar width by status
            if status == "COMPLETED":
                bar_w = int(bar_area_w * 0.88)
            elif status == "RUNNING":
                bar_w = int(bar_area_w * 0.55)
            elif status == "FAILED":
                bar_w = int(bar_area_w * 0.92)
            else:
                bar_w = int(bar_area_w * 0.15)

            bar_x = label_w
            track_h = 10
            track_y = y + (row_h - track_h) // 2

            # Track background
            track_bg = QColor(Colors.BG_ELEVATED)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(track_bg)
            p.drawRoundedRect(bar_x, track_y, bar_area_w, track_h, self._BAR_CORNER, self._BAR_CORNER)

            # Fill bar
            fill_color = QColor(status_hex)
            fill_color.setAlpha(220)
            p.setBrush(fill_color)
            p.drawRoundedRect(bar_x, track_y, max(bar_w, 8), track_h, self._BAR_CORNER, self._BAR_CORNER)

            # Status badge pill
            badge_w = 80
            badge_h = 20
            badge_x = bar_x + bar_w + 12
            badge_y = y + (row_h - badge_h) // 2

            badge_bg = QColor(status_hex)
            badge_bg.setAlpha(28)
            p.setBrush(badge_bg)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, badge_h // 2, badge_h // 2)

            p.setPen(color)
            badge_font = QFont("Inter", 8, QFont.Weight.Bold)
            p.setFont(badge_font)
            p.drawText(
                QRectF(badge_x, badge_y, badge_w, badge_h),
                Qt.AlignmentFlag.AlignCenter,
                status,
            )
