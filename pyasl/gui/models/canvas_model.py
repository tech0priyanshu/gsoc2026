"""
gui/models/canvas_model.py
---------------------------
Pure data model for the DAG canvas.

``CanvasNode`` holds per-node state (position, status, edges).
``CanvasGraph`` manages the collection and provides mutation helpers
used by both the controller and the view.

No Qt widget imports — only ``QRect`` / ``QPoint`` for hit-testing geometry.
"""
from __future__ import annotations

from typing import Dict, List, Optional

try:
    from PyQt6.QtCore import QRect, QPoint  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import NODE_WIDTH, NODE_HEIGHT


# ---------------------------------------------------------------------------
# CanvasNode
# ---------------------------------------------------------------------------

class CanvasNode:
    """A single node on the pipeline canvas."""

    __slots__ = ("node_id", "function_name", "x", "y", "status", "depends_on")

    def __init__(
        self,
        node_id: str,
        function_name: str,
        x: int = 100,
        y: int = 100,
    ) -> None:
        self.node_id = node_id
        self.function_name = function_name
        self.x = x
        self.y = y
        self.status: str = "PENDING"
        self.depends_on: List[str] = []

    @property
    def rect(self) -> QRect:
        return QRect(self.x, self.y, NODE_WIDTH, NODE_HEIGHT)

    def contains(self, point: QPoint) -> bool:
        return self.rect.contains(point)


# ---------------------------------------------------------------------------
# CanvasGraph
# ---------------------------------------------------------------------------

class CanvasGraph:
    """
    Manages the full collection of ``CanvasNode`` objects and their edges.

    This is the **data** layer — it knows nothing about rendering.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, CanvasNode] = {}

    # -- mutation ----------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        function_name: str,
        x: int = 100,
        y: int = 100,
    ) -> bool:
        """Add a node. Returns ``False`` if *node_id* already exists."""
        if node_id in self.nodes:
            return False
        self.nodes[node_id] = CanvasNode(node_id, function_name, x, y)
        return True

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and clean up dangling edges. Returns ``False`` if missing."""
        if node_id not in self.nodes:
            return False
        del self.nodes[node_id]
        for n in self.nodes.values():
            if node_id in n.depends_on:
                n.depends_on.remove(node_id)
        return True

    def add_edge(self, source_id: str, target_id: str) -> bool:
        """Add dependency: *target* depends on *source*. Returns ``False`` if duplicate."""
        if target_id not in self.nodes or source_id not in self.nodes:
            return False
        target = self.nodes[target_id]
        if source_id in target.depends_on:
            return False
        target.depends_on.append(source_id)
        return True

    def clear_dependencies(self, node_id: str) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].depends_on = []

    def clear(self) -> None:
        self.nodes.clear()

    def set_node_status(self, node_id: str, status: str) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].status = status

    # -- queries -----------------------------------------------------------

    def node_at(self, point: QPoint) -> Optional[str]:
        """Hit-test: return the *node_id* under *point*, or ``None``."""
        for nid, node in self.nodes.items():
            if node.contains(point):
                return nid
        return None

    def to_pipeline_spec(self, config_provider=None) -> List[Dict]:
        """Serialise graph into a list of dicts for pipeline construction."""
        res = []
        for n in self.nodes.values():
            item = {
                "id": n.node_id,
                "function": n.function_name,
                "depends_on": list(n.depends_on),
            }
            if config_provider is not None:
                item["config"] = config_provider(n.node_id) or {}
            res.append(item)
        return res

    def auto_position(self, count: int) -> tuple[int, int]:
        """Suggest an (x, y) position for the *count*-th node."""
        x = 40 + (count % 4) * 210
        y = 40 + (count // 4) * 100
        return x, y
