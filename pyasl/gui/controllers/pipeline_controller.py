"""
gui/controllers/pipeline_controller.py
----------------------------------------
Business-logic controller for the Pipeline Builder tab.

Owns the ``CanvasGraph`` and ``PipelineState`` models and provides
high-level operations: add/remove nodes, load/save YAML, validate, run.
Emits Qt signals that views connect to.

Integrates with ``SessionManager`` for auto-save persistence of the
pipeline graph and node configurations across restarts.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.models.canvas_model import CanvasGraph
from pyasl.gui.models.pipeline_state import PipelineState
from pyasl.gui.constants import DEFAULT_PALETTE_FUNCTIONS


class PipelineController(QObject):
    """
    Signals
    -------
    graph_changed()                  — node added/removed or edge changed
    node_status_changed(node_id, s)  — status updated during run
    run_started()
    run_completed(summary_str)
    error(message)
    palette_loaded(names_list)
    """

    graph_changed = pyqtSignal()
    node_status_changed = pyqtSignal(str, str)
    run_started = pyqtSignal()
    run_completed = pyqtSignal(str)
    error = pyqtSignal(str)
    palette_loaded = pyqtSignal(list)

    def __init__(self, parent=None, session=None):
        super().__init__(parent)
        self.graph = CanvasGraph()
        self.state = PipelineState()
        self._worker = None
        self._session = session          # SessionManager (optional)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _auto_save_session(self) -> None:
        """Persist current pipeline state to the session file."""
        if self._session is None:
            return
        nodes_data = []
        for nid, node in self.graph.nodes.items():
            nodes_data.append({
                "node_id": node.node_id,
                "function_name": node.function_name,
                "x": node.x,
                "y": node.y,
                "depends_on": list(node.depends_on),
                "config": self.state.get_config(nid),
            })
        self._session.set_pipeline({"nodes": nodes_data})

    # ------------------------------------------------------------------
    # Restore from session
    # ------------------------------------------------------------------

    def restore_pipeline(self, pipeline_data: Dict[str, Any]) -> None:
        """
        Repopulate ``CanvasGraph`` and ``PipelineState`` from previously
        saved session data.
        """
        self.graph.clear()
        self.state.clear()

        for nd in pipeline_data.get("nodes", []):
            nid = nd.get("node_id", "")
            fn = nd.get("function_name", "")
            x = nd.get("x", 100)
            y = nd.get("y", 100)
            if nid and fn:
                self.graph.add_node(nid, fn, x, y)
                self.graph.nodes[nid].depends_on = list(
                    nd.get("depends_on", [])
                )
                self.state.set_config(nid, nd.get("config", {}))

        self.graph_changed.emit()

    # ------------------------------------------------------------------
    # Palette
    # ------------------------------------------------------------------

    def load_palette(self) -> List[str]:
        """Return sorted list of available function names for the palette.

        Emits default items immediately, then loads the registry
        in a background thread so the UI appears without delay.
        """
        # Emit defaults right away so the palette is usable immediately
        defaults = sorted(DEFAULT_PALETTE_FUNCTIONS)
        self.palette_loaded.emit(defaults)

        # Load registry items asynchronously
        from PyQt6.QtCore import QThread, pyqtSignal as _Signal

        class _RegistryLoader(QThread):
            done = _Signal(list)

            def run(self):
                try:
                    from pyasl.pipeline.registry import registry
                    names = registry.list_registered()
                except Exception:
                    names = []
                all_names = sorted(set(names) | set(DEFAULT_PALETTE_FUNCTIONS))
                self.done.emit(all_names)

        self._palette_loader = _RegistryLoader()
        self._palette_loader.done.connect(self.palette_loaded.emit)
        self._palette_loader.start()
        return defaults

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        function_name: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> bool:
        if x is None or y is None:
            x, y = self.graph.auto_position(len(self.graph.nodes))
        added = self.graph.add_node(node_id, function_name, x, y)
        if added:
            self.state.set_config(node_id, {})
            self.graph_changed.emit()
            self._auto_save_session()
        return added

    def add_node_from_palette(self, function_name: str) -> str:
        """Auto-generate a node_id and add to graph. Returns the node_id."""
        existing = [n for n in self.graph.nodes if n.startswith(function_name[:8])]
        node_id = f"{function_name[:8]}_{len(existing) + 1}"
        x, y = self.graph.auto_position(len(self.graph.nodes))
        self.graph.add_node(node_id, function_name, x, y)
        self.state.set_config(node_id, {})
        self.graph_changed.emit()
        self._auto_save_session()
        return node_id

    def remove_node(self, node_id: str) -> None:
        self.graph.remove_node(node_id)
        self.state.remove_config(node_id)
        self.graph_changed.emit()
        self._auto_save_session()

    def clear(self) -> None:
        self.graph.clear()
        self.state.clear()
        self.graph_changed.emit()
        self._auto_save_session()

    def connect_nodes(self, source_id: str, target_id: str) -> bool:
        added = self.graph.add_edge(source_id, target_id)
        if added:
            self.graph_changed.emit()
            self._auto_save_session()
        return added

    def clear_dependencies(self, node_id: str) -> None:
        self.graph.clear_dependencies(node_id)
        self.graph_changed.emit()
        self._auto_save_session()

    # ------------------------------------------------------------------
    # YAML I/O
    # ------------------------------------------------------------------

    def load_yaml(self, path: str) -> None:
        """Load a pipeline YAML into the graph. Emits ``graph_changed`` or ``error``."""
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            self.graph.clear()
            self.state.clear()
            
            if isinstance(data, dict) and "steps" in data:
                steps_data = data.get("steps", [])
                prev_id = None
                for i, n in enumerate(steps_data):
                    if not isinstance(n, dict):
                        continue
                    fn = n.get("module") or n.get("name") or n.get("function", f"step_{i}")
                    nid = n.get("id") or fn
                    
                    # Avoid duplicate ids
                    base_nid = nid
                    suffix = 1
                    while nid in self.graph.nodes:
                        nid = f"{base_nid}_{suffix}"
                        suffix += 1
                        
                    x, y = self.graph.auto_position(i)
                    self.graph.add_node(nid, fn, x, y)
                    self.state.set_config(nid, n.get("params") or n.get("config", {}))
                    
                    deps = n.get("depends_on")
                    if deps is not None:
                        if isinstance(deps, str):
                            deps = [deps]
                        self.graph.nodes[nid].depends_on = list(deps)
                    elif prev_id:
                        self.graph.nodes[nid].depends_on = [prev_id]
                    prev_id = nid
            else:
                nodes_data = data.get("nodes", []) if isinstance(data, dict) else []
                for i, n in enumerate(nodes_data):
                    nid = n.get("id", f"node_{i}")
                    fn = n.get("function", "")
                    x, y = self.graph.auto_position(i)
                    self.graph.add_node(nid, fn, x, y)
                    self.state.set_config(nid, n.get("config", {}))
                    deps = n.get("depends_on", [])
                    self.graph.nodes[nid].depends_on = deps
            self.graph_changed.emit()
            self._auto_save_session()
        except Exception as exc:
            self.error.emit(f"Load Error: {exc}")

    def save_yaml(self, path: str) -> None:
        """Save current graph to YAML including node configs. Emits ``error`` on failure."""
        try:
            import yaml
            spec = self.graph.to_pipeline_spec(config_provider=self.state.get_config)
            data = {"pipeline": {"name": "gui_pipeline"}, "nodes": spec}
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as exc:
            self.error.emit(f"Save Error: {exc}")

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate(self) -> Optional[str]:
        """
        Validate the current graph. Returns ``None`` on success,
        or an error message string on failure.
        """
        spec = self.graph.to_pipeline_spec()
        if not spec:
            return "No nodes on the canvas."
        try:
            from pyasl.pipeline.validator import validate_pipeline
            validate_pipeline(spec)
            return None
        except Exception as exc:
            return str(exc)

    # ------------------------------------------------------------------
    # Run pipeline
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build and execute the pipeline in a background thread with pre-flight check."""
        spec = self.graph.to_pipeline_spec()
        if not spec:
            self.error.emit("No nodes on the canvas.")
            return

        try:
            from pyasl.pipeline.validator import pre_flight_check
            pre_flight_check(spec)
        except Exception as exc:
            self.error.emit(f"Pre-flight Validation Error: {exc}")
            return

        try:
            from pyasl.pipeline.pipeline import Pipeline
            from pyasl.pipeline.node import Node
            from pyasl.gui.threads.pipeline_worker import PipelineWorkerThread

            pl = Pipeline("gui_pipeline")
            for s in spec:
                cfg = self.state.get_config(s["id"])
                pl.add_node(Node(
                    node_id=s["id"],
                    function_name=s["function"],
                    depends_on=s["depends_on"],
                    config=cfg,
                ))

            self._worker = PipelineWorkerThread(pl)
            self._worker.node_started.connect(
                lambda nid: self._on_node_status(nid, "RUNNING")
            )
            self._worker.node_finished.connect(self._on_node_status)
            self._worker.pipeline_done.connect(self._on_done)
            self._worker.error_occurred.connect(self.error.emit)
            self.run_started.emit()
            self._worker.start()
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_node_status(self, node_id: str, status: str) -> None:
        self.graph.set_node_status(node_id, status)
        self.node_status_changed.emit(node_id, status)

    def _on_done(self, result: dict) -> None:
        self.state.set_result(result)
        self.run_completed.emit(self.state.format_result_summary())
        self._auto_save_session()
