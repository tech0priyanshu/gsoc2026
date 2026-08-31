"""
gui/models/pipeline_state.py
------------------------------
Tracks per-node configuration and execution results for a pipeline run.
Pure data — no Qt widgets.
"""
from __future__ import annotations

from typing import Dict, Optional


class PipelineState:
    """
    Holds the mutable state associated with a pipeline session.

    * ``node_configs``  — user-entered config dicts keyed by node_id
    * ``last_result``   — result dict from the most recent execution
    """

    def __init__(self) -> None:
        self.node_configs: Dict[str, dict] = {}
        self.last_result: Optional[dict] = None

    # -- config management -------------------------------------------------

    def set_config(self, node_id: str, config: dict) -> None:
        self.node_configs[node_id] = config

    def get_config(self, node_id: str) -> dict:
        return self.node_configs.get(node_id, {})

    def remove_config(self, node_id: str) -> None:
        self.node_configs.pop(node_id, None)

    def clear(self) -> None:
        self.node_configs.clear()
        self.last_result = None

    # -- execution result --------------------------------------------------

    def set_result(self, result: dict) -> None:
        self.last_result = result

    def format_result_summary(self) -> str:
        """Human-readable one-liner for the last run."""
        if not self.last_result:
            return "No run yet"
        if isinstance(self.last_result, dict):
            status = self.last_result.get("status", "?")
            dur = self.last_result.get("duration", 0)
            nodes = len(self.last_result.get("nodes", {}))
            return f"Pipeline {status}  |  {dur:.2f}s  |  {nodes} nodes executed"
        return f"Pipeline {self.last_result}"
