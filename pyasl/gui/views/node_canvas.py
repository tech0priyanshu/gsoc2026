"""
gui/views/node_canvas.py
--------------------------
Interactive DAG canvas widget for the Pipeline Builder.

Renders the ``CanvasGraph`` model and handles mouse interaction
(drag, select, connect, right-click context menu).
All mutations go through the ``PipelineController``.
"""
from __future__ import annotations

import math
from typing import Optional

try:
    from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal  # type: ignore
    from PyQt6.QtGui import (  # type: ignore
        QPainter, QPen, QColor, QFont, QPainterPath,
        QLinearGradient,
    )
    from PyQt6.QtWidgets import QWidget, QMenu, QPushButton  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import (
    Colors, STATUS_COLORS, NODE_WIDTH, NODE_HEIGHT, GRID_STEP,
)
from pyasl.gui.models.canvas_model import CanvasGraph, CanvasNode

# Pre-built QColors for painting
_BG = None
_PANEL = None
_BORDER = None
_ACCENT = None
_TEXT = None
_MUTED = None
_Q_STATUS_COLORS = {}

def update_colors():
    global _BG, _PANEL, _BORDER, _ACCENT, _TEXT, _MUTED, _Q_STATUS_COLORS
    _BG = QColor(Colors.BG_PRIMARY)
    _PANEL = QColor(Colors.BG_PANEL)
    _BORDER = QColor(Colors.BORDER)
    _ACCENT = QColor(Colors.DARK_PURPLE)
    _TEXT = QColor(Colors.TEXT_PRIMARY)
    _MUTED = QColor(Colors.TEXT_MUTED)
    _Q_STATUS_COLORS = {k: QColor(v) for k, v in STATUS_COLORS.items()}

update_colors()


class NodeCanvasView(QWidget):
    """
    Pure rendering + mouse interaction for the DAG canvas.

    Reads from a ``CanvasGraph`` model; delegates mutations to
    the ``PipelineController`` via signals.

    Signals
    -------
    node_clicked(node_id)
    node_connect_requested(source_id, target_id)
    node_remove_requested(node_id)
    node_clear_deps_requested(node_id)
    node_moved(node_id, x, y)
    """

    node_clicked = pyqtSignal(str)
    node_connect_requested = pyqtSignal(str, str)
    node_remove_requested = pyqtSignal(str)
    node_clear_deps_requested = pyqtSignal(str)
    node_moved = pyqtSignal(str, int, int)

    def __init__(self, graph: CanvasGraph, parent=None):
        super().__init__(parent)
        self._graph = graph
        self._selected: Optional[str] = None
        self._dragging: Optional[str] = None
        self._drag_offset = QPoint()
        self._connecting: Optional[str] = None
        self._mouse_pos = QPoint()
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self._panning = False
        self._pan_start = QPoint()
        
        # Floating zoom controls overlay
        self.btn_zoom_in = QPushButton("+", self)
        self.btn_zoom_out = QPushButton("-", self)
        self.btn_zoom_fit = QPushButton("🔍", self)
        
        for btn in (self.btn_zoom_in, self.btn_zoom_out, self.btn_zoom_fit):
            btn.setFixedSize(30, 30)
            
        self.update_overlay_style()
        
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        self.btn_zoom_fit.clicked.connect(self.zoom_fit)

        # Reduced minimum so the canvas works on smaller windows
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def update_overlay_style(self):
        btn_style = (
            f"QPushButton {{"
            f"  background: {Colors.BG_PANEL};"
            f"  color: {Colors.TEXT_PRIMARY};"
            f"  border: 1px solid {Colors.BORDER};"
            f"  border-radius: 4px;"
            f"  font-weight: bold;"
            f"  font-size: 14px;"
            f"  padding: 0px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {Colors.BG_HOVER};"
            f"}}"
        )
        for btn in (self.btn_zoom_in, self.btn_zoom_out, self.btn_zoom_fit):
            btn.setStyleSheet(btn_style)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        padding = 10
        btn_w, btn_h = 30, 30
        x = self.width() - btn_w - padding
        y_start = padding
        self.btn_zoom_in.move(x, y_start)
        self.btn_zoom_out.move(x, y_start + btn_h + 5)
        self.btn_zoom_fit.move(x, y_start + (btn_h + 5) * 2)

    def to_canvas_coords(self, point: QPoint) -> QPoint:
        x = (point.x() - self._pan_offset.x()) / self._zoom_factor
        y = (point.y() - self._pan_offset.y()) / self._zoom_factor
        return QPoint(int(x), int(y))

    @property
    def selected_node_id(self) -> Optional[str]:
        return self._selected

    # ------------------------------------------------------------------
    # Mouse and Wheel events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        pos = event.pos()
        canvas_pos = self.to_canvas_coords(pos)
        hit = self._graph.node_at(canvas_pos)

        if event.button() == Qt.MouseButton.LeftButton:
            if hit:
                mods = event.modifiers()
                if mods & Qt.KeyboardModifier.ControlModifier and self._connecting is None:
                    self._connecting = hit
                elif self._connecting and hit != self._connecting:
                    self.node_connect_requested.emit(self._connecting, hit)
                    self._connecting = None
                    self.update()
                else:
                    self._connecting = None
                    self._dragging = hit
                    n = self._graph.nodes[hit]
                    self._drag_offset = canvas_pos - QPoint(n.x, n.y)
                    self._selected = hit
                    self.node_clicked.emit(hit)
                    self.update()
            else:
                self._connecting = None
                self._selected = None
                self._panning = True
                self._pan_start = pos
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()

        elif event.button() == Qt.MouseButton.RightButton:
            if hit:
                self._show_context_menu(hit, event.globalPosition().toPoint())

        elif event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = pos
            self.update()

    def mouseMoveEvent(self, event):
        self._mouse_pos = self.to_canvas_coords(event.pos())
        if self._dragging:
            n = self._graph.nodes[self._dragging]
            new_pos = self._mouse_pos - self._drag_offset
            n.x = max(0, new_pos.x())
            n.y = max(0, new_pos.y())
            self.update()
        elif self._panning:
            diff = event.pos() - self._pan_start
            self._pan_offset += diff
            self._pan_start = event.pos()
            self.update()
        elif self._connecting:
            self.update()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            n = self._graph.nodes.get(self._dragging)
            if n:
                self.node_moved.emit(self._dragging, n.x, n.y)
        self._dragging = None
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()

    def wheelEvent(self, event):
        # Zoom centered around mouse pointer
        mouse_widget_pos = event.position().toPoint()
        old_canvas_pos = self.to_canvas_coords(mouse_widget_pos)
        
        angle = event.angleDelta().y()
        zoom_step = 1.15
        if angle > 0:
            new_zoom = self._zoom_factor * zoom_step
        else:
            new_zoom = self._zoom_factor / zoom_step
            
        new_zoom = max(0.2, min(5.0, new_zoom))
        self._zoom_factor = new_zoom
        self._pan_offset = mouse_widget_pos - old_canvas_pos * self._zoom_factor
        self.update()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, node_id: str, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {Colors.BG_PANEL}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 8px; }}"
            f"QMenu::item {{ padding: 6px 16px; color: {Colors.TEXT_PRIMARY}; }}"
            f"QMenu::item:selected {{ background: {Colors.BG_HOVER}; }}"
        )
        del_action = menu.addAction(f"🗑  Remove '{node_id}'")
        clr_action = menu.addAction("✂  Clear all dependencies")
        chosen = menu.exec(global_pos)
        if chosen == del_action:
            self.node_remove_requested.emit(node_id)
        elif chosen == clr_action:
            self.node_clear_deps_requested.emit(node_id)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(self.rect(), _BG)

        # Apply camera translation and scaling
        p.save()
        p.translate(self._pan_offset)
        p.scale(self._zoom_factor, self._zoom_factor)

        # Grid
        self._draw_grid(p)

        # Dependency arrows
        for n in self._graph.nodes.values():
            for dep_id in n.depends_on:
                if dep_id in self._graph.nodes:
                    self._draw_arrow(p, self._graph.nodes[dep_id], n)

        # In-progress arrow (Ctrl+drag)
        if self._connecting and self._connecting in self._graph.nodes:
            src = self._graph.nodes[self._connecting]
            self._draw_arrow_to_point(p, src, self._mouse_pos)

        # Nodes
        for n in self._graph.nodes.values():
            self._draw_node(p, n)

        p.restore()

        # Draw zoom indicator overlay
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(Colors.TEXT_MUTED))
        zoom_text = f"Zoom: {int(self._zoom_factor * 100)}%"
        p.drawText(
            self.rect().adjusted(0, 0, -10, -10),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            zoom_text
        )

    def _draw_grid(self, p: QPainter) -> None:
        pen = QPen(QColor(Colors.BORDER_SUBTLE), 1)
        p.setPen(pen)
        
        tl = self.to_canvas_coords(QPoint(0, 0))
        br = self.to_canvas_coords(QPoint(self.width(), self.height()))
        
        start_x = (tl.x() // GRID_STEP) * GRID_STEP
        end_x = ((br.x() // GRID_STEP) + 1) * GRID_STEP
        start_y = (tl.y() // GRID_STEP) * GRID_STEP
        end_y = ((br.y() // GRID_STEP) + 1) * GRID_STEP
        
        for x in range(start_x, end_x, GRID_STEP):
            p.drawLine(x, tl.y(), x, br.y())
        for y in range(start_y, end_y, GRID_STEP):
            p.drawLine(tl.x(), y, br.x(), y)

    def zoom_in(self):
        center = QPoint(self.width() // 2, self.height() // 2)
        old_canvas_center = self.to_canvas_coords(center)
        self._zoom_factor = min(5.0, self._zoom_factor * 1.25)
        self._pan_offset = center - old_canvas_center * self._zoom_factor
        self.update()

    def zoom_out(self):
        center = QPoint(self.width() // 2, self.height() // 2)
        old_canvas_center = self.to_canvas_coords(center)
        self._zoom_factor = max(0.2, self._zoom_factor / 1.25)
        self._pan_offset = center - old_canvas_center * self._zoom_factor
        self.update()

    def zoom_fit(self):
        if not self._graph.nodes:
            self._zoom_factor = 1.0
            self._pan_offset = QPoint(0, 0)
            self.update()
            return

        min_x = min(n.x for n in self._graph.nodes.values())
        min_y = min(n.y for n in self._graph.nodes.values())
        max_x = max(n.x + NODE_WIDTH for n in self._graph.nodes.values())
        max_y = max(n.y + NODE_HEIGHT for n in self._graph.nodes.values())

        graph_width = max_x - min_x
        graph_height = max_y - min_y

        padding = 40
        padded_width = graph_width + 2 * padding
        padded_height = graph_height + 2 * padding

        widget_w = self.width()
        widget_h = self.height()

        zoom_x = widget_w / padded_width
        zoom_y = widget_h / padded_height
        zoom = min(zoom_x, zoom_y)
        zoom = max(0.2, min(2.0, zoom))

        self._zoom_factor = zoom

        center_x = min_x + graph_width / 2
        center_y = min_y + graph_height / 2

        self._pan_offset = QPoint(
            int(widget_w / 2 - center_x * zoom),
            int(widget_h / 2 - center_y * zoom)
        )
        self.update()

    def _draw_node(self, p: QPainter, n: CanvasNode) -> None:
        r = n.rect
        is_selected = n.node_id == self._selected
        status_col = _Q_STATUS_COLORS.get(n.status, _MUTED)

        # Drop shadow
        shadow_r = r.adjusted(4, 4, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawRoundedRect(shadow_r, 10, 10)

        # Node body gradient
        grad = QLinearGradient(
            r.topLeft().toPointF(), r.bottomLeft().toPointF(),
        )
        grad.setColorAt(0, QColor(Colors.BG_ELEVATED))
        grad.setColorAt(1, QColor(Colors.BG_PANEL))
        p.setBrush(grad)

        # Border
        border_color = (
            _ACCENT if is_selected
            else status_col if n.status != "PENDING"
            else _BORDER
        )
        p.setPen(QPen(border_color, 2 if is_selected else 1))
        p.drawRoundedRect(r, 10, 10)

        # Status dot
        dot_x = r.left() + 12
        dot_y = r.top() + r.height() // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(status_col)
        p.drawEllipse(dot_x - 5, dot_y - 5, 10, 10)

        # Node ID label
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.setPen(_TEXT)
        text_r = r.adjusted(25, 4, -8, -28)
        p.drawText(
            text_r,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            n.node_id,
        )

        # Function name label (smaller, muted)
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(_MUTED)
        func_r = r.adjusted(25, 26, -8, -4)
        p.drawText(
            func_r,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            n.function_name,
        )

        # Left accent bar
        if n.status != "PENDING":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(status_col)
            bar = QRect(r.left(), r.top() + 8, 3, r.height() - 16)
            p.drawRoundedRect(bar, 2, 2)

    def _draw_arrow(
        self, p: QPainter, src: CanvasNode, dst: CanvasNode,
    ) -> None:
        sx = src.x + NODE_WIDTH
        sy = src.y + NODE_HEIGHT // 2
        dx = dst.x
        dy = dst.y + NODE_HEIGHT // 2
        self._draw_bezier_arrow(p, sx, sy, dx, dy, _ACCENT)

    def _draw_arrow_to_point(
        self, p: QPainter, src: CanvasNode, pt: QPoint,
    ) -> None:
        sx = src.x + NODE_WIDTH
        sy = src.y + NODE_HEIGHT // 2
        self._draw_bezier_arrow(
            p, sx, sy, pt.x(), pt.y(),
            QColor(Colors.DARK_PURPLE), dashed=True,
        )

    def _draw_bezier_arrow(
        self, p: QPainter, x1, y1, x2, y2,
        color: QColor, dashed: bool = False,
    ) -> None:
        pen = QPen(color, 2)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cp_offset = min(abs(x2 - x1) * 0.5, 120)
        path = QPainterPath()
        path.moveTo(x1, y1)
        path.cubicTo(x1 + cp_offset, y1, x2 - cp_offset, y2, x2, y2)
        p.drawPath(path)

        # Arrow head
        angle = math.atan2(y2 - (y2 + y1) / 2, x2 - (x2 + x1) / 2)
        a_len = 10
        a_angle = math.pi / 6
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        arrow = QPainterPath()
        arrow.moveTo(x2, y2)
        arrow.lineTo(
            x2 - a_len * math.cos(angle - a_angle),
            y2 - a_len * math.sin(angle - a_angle),
        )
        arrow.lineTo(
            x2 - a_len * math.cos(angle + a_angle),
            y2 - a_len * math.sin(angle + a_angle),
        )
        arrow.closeSubpath()
        p.drawPath(arrow)
