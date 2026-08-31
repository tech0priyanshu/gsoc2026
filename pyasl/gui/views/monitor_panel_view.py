"""
gui/views/monitor_panel_view.py
---------------------------------
Execution Monitor tab view — complete UI refactor.

Layout (top → bottom):
  1. Header row  — title/subtitle left · Export Logs + Clear right
  2. Metric cards — 4 compact cards (Total · Completed · Failed · Duration)
  3. Main content — 70 % Timeline card  |  30 % Execution Summary panel
  4. Live Logs    — full-width dark terminal with sticky toolbar

All public API, signal wiring, state management and backend code
is unchanged from the previous version.
"""
from __future__ import annotations

import json
from typing import Dict, List

try:
    from PyQt6.QtCore import Qt, QTimer  # type: ignore
    from PyQt6.QtGui import QFont  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
        QPlainTextEdit, QLabel, QPushButton, QGroupBox,
        QScrollArea, QComboBox, QFileDialog, QLineEdit,
        QFrame, QSizePolicy,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import Colors
from pyasl.gui.views.components.summary_bar import SummaryBar
from pyasl.gui.views.components.node_timeline import NodeTimelineWidget
from pyasl.gui.views.components.execution_summary_panel import ExecutionSummaryPanel


# ---------------------------------------------------------------------------
# Thin divider helper
# ---------------------------------------------------------------------------

class _VDivider(QFrame):
    """1-px vertical divider for the log toolbar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFixedWidth(1)
        self.setFixedHeight(22)
        self.setStyleSheet(f"background: {Colors.BORDER}; border: none;")


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

class MonitorPanelView(QWidget):
    """
    Execution Monitor tab.

    Can be connected to ``PipelineController`` signals
    (``node_status_changed``) externally by the main window.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_entries: List[str] = []
        self._node_stats: Dict[str, str] = {}
        self._auto_scroll: bool = True
        self._execution_session = None      # Set via set_execution_session()
        self._setup_ui()

        # Poll structured logger queue every 200 ms (pipeline runs)
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._drain_log_queue)
        self._timer.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)

        # ── Row 0: Header ─────────────────────────────────────────────
        root.addLayout(self._build_header())
        root.addSpacing(20)

        # ── Row 1: Metric Cards ────────────────────────────────────────
        self._summary = SummaryBar()
        root.addWidget(self._summary)
        root.addSpacing(20)

        # ── Row 2: Timeline (70%) + Summary Panel (30%) ────────────────
        root.addLayout(self._build_main_content(), stretch=3)
        root.addSpacing(20)

        # ── Row 3: Live Logs terminal ──────────────────────────────────
        root.addWidget(self._build_log_terminal(), stretch=2)

        # Apply overarching page background
        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(0)

        # Title + Subtitle
        title_col = QVBoxLayout()
        title_col.setSpacing(3)

        self._title_lbl = QLabel("Execution Monitor")
        self._title_lbl.setStyleSheet(
            f"font-size: 32px; font-weight: 800; color: {Colors.TEXT_PRIMARY}; "
            f"font-family: 'Inter', 'Segoe UI', sans-serif;"
        )

        self._subtitle_lbl = QLabel("Monitor workflow execution in real time.")
        self._subtitle_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 400; color: {Colors.TEXT_MUTED}; "
            f"font-family: 'Inter', 'Segoe UI', sans-serif;"
        )

        title_col.addWidget(self._title_lbl)
        title_col.addWidget(self._subtitle_lbl)

        hdr.addLayout(title_col)
        hdr.addStretch()

        # Action buttons (right-aligned, minimal)
        self._sync_btn = QPushButton("🔄  Sync Batch Data")
        self._sync_btn.setFixedHeight(34)
        self._sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_btn.setToolTip("Synchronize Monitor with current Batch Mode execution queue & history")
        self._sync_btn.clicked.connect(self._on_sync_clicked)

        self._export_btn = QPushButton("⬇  Export Logs")
        self._export_btn.setFixedHeight(34)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.clicked.connect(self._export_log)

        self._clear_btn = QPushButton("✕  Clear")
        self._clear_btn.setFixedHeight(34)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear)

        hdr.addWidget(self._sync_btn)
        hdr.addSpacing(8)
        hdr.addWidget(self._export_btn)
        hdr.addSpacing(8)
        hdr.addWidget(self._clear_btn)

        return hdr

    # ------------------------------------------------------------------
    # Main content — 70 / 30 split
    # ------------------------------------------------------------------

    def _build_main_content(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        # ── Left: Execution Timeline card (70%) ───────────────────────
        self._tl_card = QGroupBox()
        tl_lay = QVBoxLayout(self._tl_card)
        tl_lay.setContentsMargins(16, 14, 16, 14)
        tl_lay.setSpacing(12)

        # Timeline card header
        tl_hdr = QVBoxLayout()
        tl_hdr.setSpacing(2)

        tl_title = QLabel("Execution Timeline")
        tl_title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"font-family: 'Inter', 'Segoe UI', sans-serif;"
        )
        tl_sub = QLabel("Real-time progress across pipeline nodes.")
        tl_sub.setStyleSheet(
            f"font-size: 12px; color: {Colors.TEXT_MUTED}; "
            f"font-family: 'Inter', 'Segoe UI', sans-serif;"
        )
        tl_hdr.addWidget(tl_title)
        tl_hdr.addWidget(tl_sub)
        tl_lay.addLayout(tl_hdr)

        # Thin divider below header
        tl_div = QFrame()
        tl_div.setFrameShape(QFrame.Shape.HLine)
        tl_div.setFixedHeight(1)
        tl_div.setStyleSheet(f"background: {Colors.BORDER}; border: none;")
        tl_lay.addWidget(tl_div)

        # Timeline widget in a scroll area
        self._timeline = NodeTimelineWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._timeline)
        scroll.setMinimumHeight(160)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: transparent; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        tl_lay.addWidget(scroll, stretch=1)

        row.addWidget(self._tl_card, stretch=7)

        # ── Right: Execution Summary panel (30%) ──────────────────────
        self._exec_summary = ExecutionSummaryPanel()
        self._exec_summary.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

        row.addWidget(self._exec_summary, stretch=3)

        return row

    # ------------------------------------------------------------------
    # Log terminal
    # ------------------------------------------------------------------

    def _build_log_terminal(self) -> QGroupBox:
        self._log_card = QGroupBox()
        lay = QVBoxLayout(self._log_card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Sticky toolbar ─────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setObjectName("log_toolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(14, 10, 14, 10)
        tb_lay.setSpacing(8)

        # Section title
        log_title = QLabel("Live Logs")
        log_title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {Colors.TEXT_PRIMARY}; "
            f"font-family: 'Inter', 'Segoe UI', sans-serif;"
        )
        tb_lay.addWidget(log_title)
        tb_lay.addSpacing(4)

        tb_lay.addWidget(_VDivider())
        tb_lay.addSpacing(4)

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Search logs…")
        self._search_input.setFixedWidth(180)
        self._search_input.setFixedHeight(30)
        self._search_input.textChanged.connect(self._refilter_log)
        tb_lay.addWidget(self._search_input)

        # Level filter
        self._level_filter = QComboBox()
        self._level_filter.setFixedHeight(30)
        self._level_filter.setFixedWidth(105)
        for item in ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"]:
            self._level_filter.addItem(item)
        self._level_filter.currentTextChanged.connect(self._refilter_log)
        tb_lay.addWidget(self._level_filter)

        tb_lay.addWidget(_VDivider())

        # Auto-scroll toggle
        self._scroll_toggle_btn = QPushButton("↓ Auto-Scroll")
        self._scroll_toggle_btn.setCheckable(True)
        self._scroll_toggle_btn.setChecked(True)
        self._scroll_toggle_btn.setFixedHeight(30)
        self._scroll_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scroll_toggle_btn.clicked.connect(self._toggle_autoscroll)
        tb_lay.addWidget(self._scroll_toggle_btn)

        tb_lay.addStretch()

        # Clear logs button
        self._clear_logs_btn = QPushButton("⊘  Clear")
        self._clear_logs_btn.setFixedHeight(30)
        self._clear_logs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_logs_btn.clicked.connect(lambda: (
            self._log_entries.clear(), self._log_view.clear()
        ))
        tb_lay.addWidget(self._clear_logs_btn)

        # Download logs button
        self._dl_btn = QPushButton("⬇  Download")
        self._dl_btn.setFixedHeight(30)
        self._dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dl_btn.clicked.connect(self._export_log)
        tb_lay.addWidget(self._dl_btn)

        lay.addWidget(toolbar)

        # Thin divider between toolbar and terminal
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {Colors.BORDER}; border: none;")
        lay.addWidget(div)

        # ── Terminal view ──────────────────────────────────────────────
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("Consolas", 10))
        self._log_view.setPlaceholderText(
            "📄  No logs yet — logs will appear here during execution."
        )
        lay.addWidget(self._log_view, stretch=1)

        return self._log_card

    # ------------------------------------------------------------------
    # Public API (called by MainWindow signal wiring — DO NOT CHANGE)
    # ------------------------------------------------------------------

    def on_node_status_changed(self, node_id: str, status: str) -> None:
        self._node_stats[node_id] = status
        self._timeline.add_event(node_id, status)
        self._refresh_summary()

    def on_node_started(self, node_id: str) -> None:
        self.on_node_status_changed(node_id, "RUNNING")

    def on_node_finished(self, node_id: str, status: str) -> None:
        self.on_node_status_changed(node_id, status)

    def on_log_line(self, json_str: str) -> None:
        self._log_entries.append(json_str)
        self._append_log_line(json_str)

    # ------------------------------------------------------------------
    # ExecutionSession integration
    # ------------------------------------------------------------------

    def set_batch_controller(self, batch_controller) -> None:
        """Set reference to BatchController for manual syncing."""
        self._batch_controller = batch_controller

    def set_execution_session(self, session) -> None:
        """
        Connect this view to a shared ExecutionSession.

        Called once by MainWindow after construction.
        """
        self._execution_session = session
        if session is None:
            return

        # Wire signals
        session.execution_started.connect(self._on_execution_started)
        session.execution_completed.connect(self._on_execution_completed)
        session.execution_aborted.connect(self._on_execution_aborted)
        session.timeline_event.connect(self._on_timeline_event)
        session.log_entry.connect(self._on_session_log)
        session.progress_updated.connect(self._on_progress_updated)
        session.stats_updated.connect(self._on_stats_updated)

    def _on_sync_clicked(self) -> None:
        """
        Synchronise Execution Monitor with current Batch Mode data & logs.
        Reads all jobs from BatchController/BatchState, drains logs, and updates Monitor.
        """
        # Drain any pending structured logger entries first
        self._drain_log_queue()

        # Re-populate from batch controller if available
        if hasattr(self, "_batch_controller") and self._batch_controller is not None:
            jobs = self._batch_controller.state.jobs
            if self._execution_session is not None:
                self._execution_session.sync_from_batch_jobs(jobs)

        # Re-render Monitor UI (timeline, stats, logs)
        self._timeline.clear()
        self._node_stats.clear()
        self.restore_from_session()

    def restore_from_session(self) -> None:
        """
        Reconstruct the Monitor UI from stored ExecutionSession data.

        Called during startup restoration after from_dict() has loaded
        historical data into the session.
        """
        if self._execution_session is None or not self._execution_session.has_data:
            return

        es = self._execution_session

        # Reconstruct timeline
        for ev in es.timeline_events:
            self._timeline.add_event(ev.get("job_id", ""), ev.get("status", ""))

        # Reconstruct logs cleanly
        self._log_entries.clear()
        self._log_view.clear()
        for log_str in es.log_entries:
            self._log_entries.append(log_str)
            self._append_log_line(log_str)

        # Reconstruct node_stats from job_statuses
        for jid, st in es.job_statuses.items():
            self._node_stats[jid] = st

        # Update summary panels
        stats = es.get_stats()
        total = stats.get("total", 0)
        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)
        duration = stats.get("duration", 0.0)

        self._summary.update_stats(total, completed, failed, duration)
        self._exec_summary.update_stats(total, completed, failed, duration)

    # -- ExecutionSession signal handlers --

    def _on_execution_started(self, total_jobs: int) -> None:
        """Reset monitor UI at the start of a new batch."""
        self._log_entries.clear()
        self._node_stats.clear()
        self._log_view.clear()
        self._timeline.clear()
        self._summary.update_stats(total_jobs, 0, 0, 0.0)
        self._exec_summary.update_stats(total_jobs, 0, 0, 0.0)

    def _on_execution_completed(self) -> None:
        """Finalize display when batch completes."""
        if self._execution_session is not None:
            stats = self._execution_session.get_stats()
            self._summary.update_stats(
                stats["total"], stats["completed"],
                stats["failed"], stats["duration"],
            )
            self._exec_summary.update_stats(
                stats["total"], stats["completed"],
                stats["failed"], stats["duration"],
            )

    def _on_execution_aborted(self) -> None:
        """Update display when batch is aborted."""
        if self._execution_session is not None:
            stats = self._execution_session.get_stats()
            self._summary.update_stats(
                stats["total"], stats["completed"],
                stats["failed"], stats["duration"],
            )
            self._exec_summary.update_stats(
                stats["total"], stats["completed"],
                stats["failed"], stats["duration"],
            )

    def _on_timeline_event(self, job_id: str, status: str) -> None:
        """Add a batch job event to the timeline."""
        self._node_stats[job_id] = status
        self._timeline.add_event(job_id, status)

    def _on_session_log(self, json_str: str) -> None:
        """Receive a log entry from the ExecutionSession."""
        self._log_entries.append(json_str)
        self._append_log_line(json_str)

    def _on_progress_updated(
        self, total: int, running: int, completed: int, failed: int,
    ) -> None:
        """Update summary panels from ExecutionSession progress."""
        duration = 0.0
        if self._execution_session is not None:
            duration = self._execution_session.elapsed_duration
        self._summary.update_stats(total, completed, failed, duration)
        self._exec_summary.update_stats(total, completed, failed, duration)

    def _on_stats_updated(self, stats: dict) -> None:
        """Final stats push from ExecutionSession."""
        self._summary.update_stats(
            stats.get("total", 0), stats.get("completed", 0),
            stats.get("failed", 0), stats.get("duration", 0.0),
        )
        self._exec_summary.update_stats(
            stats.get("total", 0), stats.get("completed", 0),
            stats.get("failed", 0), stats.get("duration", 0.0),
        )

    # ------------------------------------------------------------------
    # Internal logic (unchanged)
    # ------------------------------------------------------------------

    def _toggle_autoscroll(self, checked: bool):
        self._auto_scroll = checked
        if checked:
            sb = self._log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _append_log_line(self, json_str: str) -> None:
        level_filter = self._level_filter.currentText()
        query = self._search_input.text().strip().lower() if hasattr(self, "_search_input") else ""

        try:
            entry = json.loads(json_str)
            level = entry.get("level", "INFO")
            if level_filter != "ALL" and level != level_filter:
                return

            ts = entry.get("timestamp", "")
            if ts and len(ts) >= 19:
                ts_str = ts[11:19]
            else:
                ts_str = ts[-8:-1] if ts else ""

            node = entry.get("node_id") or entry.get("logger", "")
            msg = entry.get("message", "")
            status = entry.get("status", "")
            func = entry.get("function", "")
            step_idx = entry.get("step_index")
            total_steps = entry.get("total_steps")
            dur_ms = entry.get("duration_ms")
            inputs = entry.get("inputs")
            outputs = entry.get("outputs")
            params = entry.get("params")

            prefix_parts = []
            if ts_str:
                prefix_parts.append(f"[{ts_str}]")
            prefix_parts.append(f"[{level[:4]}]")
            if node:
                prefix_parts.append(f"[{node}]")
            if step_idx is not None and total_steps is not None:
                prefix_parts.append(f"[Step {step_idx}/{total_steps}]")
            if status:
                prefix_parts.append(f"{status}")
            if dur_ms is not None and dur_ms > 0:
                prefix_parts.append(f"({dur_ms:.1f}ms)")

            prefix = " ".join(prefix_parts)
            line = f"{prefix}  {msg}" if prefix else msg

            details = []
            if func:
                details.append(f"Function: {func}")
            if inputs:
                details.append(f"Inputs: {inputs}")
            if outputs:
                details.append(f"Outputs: {outputs}")
            if params:
                details.append(f"Params: {params}")

            if details:
                line += "\n    │ " + " | ".join(details)

            err = entry.get("error")
            tb = entry.get("traceback")
            exc = entry.get("exception")

            if err:
                line += f"\n  Error: {err}"
            if tb:
                indented_tb = "\n".join(f"    {l}" for l in tb.strip().splitlines())
                line += f"\n  Traceback:\n{indented_tb}"
            elif exc:
                indented_exc = "\n".join(f"    {l}" for l in exc.strip().splitlines())
                line += f"\n  Exception:\n{indented_exc}"
        except Exception:
            line = json_str

        if query and query not in line.lower():
            return

        self._log_view.appendPlainText(line)
        if self._auto_scroll:
            sb = self._log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _refilter_log(self):
        self._log_view.clear()
        for entry in self._log_entries:
            self._append_log_line(entry)

    def _refresh_summary(self):
        total = len(self._node_stats)
        completed = sum(1 for s in self._node_stats.values() if s == "COMPLETED")
        failed = sum(1 for s in self._node_stats.values() if s == "FAILED")
        self._summary.update_stats(total, completed, failed, 0.0)
        self._exec_summary.update_stats(total, completed, failed, 0.0)

    def _drain_log_queue(self) -> None:
        """Poll the global structured logger queue and display entries."""
        try:
            from pyasl.pipeline.structured_logger import get_logger
            entries = get_logger().drain()
            for entry in entries:
                json_str = json.dumps(entry)
                self._log_entries.append(json_str)
                self._append_log_line(json_str)
        except Exception:
            pass

    def _clear(self) -> None:
        self._log_entries.clear()
        self._node_stats.clear()
        self._log_view.clear()
        self._timeline.clear()
        self._summary.update_stats(0, 0, 0, 0.0)
        self._exec_summary.update_stats(0, 0, 0, 0.0)

        # Also clear the shared execution session history
        if self._execution_session is not None:
            self._execution_session.clear_history()

    def _export_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Log", "pipeline_log.jsonl",
            "JSON Lines (*.jsonl);;All (*)",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self._log_entries))

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme_styles(self):
        """Apply/re-apply all inline styles using current Colors values."""
        # Page background
        self.setStyleSheet(f"background-color: {Colors.BG_PRIMARY};")

        # ── Header buttons ─────────────────────────────────────────────
        self._sync_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {Colors.BG_PANEL}; color: {Colors.TEXT_PRIMARY};"
            f"  border: 1px solid {Colors.BORDER}; border-radius: 8px;"
            f"  font-size: 12px; font-weight: 600; padding: 0 14px;"
            f"  font-family: 'Inter', 'Segoe UI', sans-serif;"
            f"}}"
            f"QPushButton:hover {{"
            f"  border-color: #6366F1; color: #6366F1;"
            f"}}"
        )
        self._export_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {Colors.BG_PANEL}; color: {Colors.TEXT_PRIMARY};"
            f"  border: 1px solid {Colors.BORDER}; border-radius: 8px;"
            f"  font-size: 12px; font-weight: 600; padding: 0 14px;"
            f"  font-family: 'Inter', 'Segoe UI', sans-serif;"
            f"}}"
            f"QPushButton:hover {{"
            f"  border-color: #6366F1; color: #6366F1;"
            f"}}"
        )
        self._clear_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: transparent; color: {Colors.TEXT_MUTED};"
            f"  border: 1px solid {Colors.BORDER}; border-radius: 8px;"
            f"  font-size: 12px; font-weight: 600; padding: 0 14px;"
            f"  font-family: 'Inter', 'Segoe UI', sans-serif;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: #FEE2E2; color: #EF4444; border-color: #EF4444;"
            f"}}"
        )

        # ── Timeline card ──────────────────────────────────────────────
        self._tl_card.setStyleSheet(
            f"QGroupBox {{"
            f"  background-color: {Colors.BG_PANEL};"
            f"  border: 1px solid {Colors.BORDER};"
            f"  border-radius: 16px;"
            f"  margin-top: 0px;"
            f"}}"
        )

        # ── Execution summary card ─────────────────────────────────────
        self._exec_summary.setStyleSheet(
            f"ExecutionSummaryPanel, QWidget {{"
            f"  background-color: {Colors.BG_PANEL};"
            f"  border: 1px solid {Colors.BORDER};"
            f"  border-radius: 16px;"
            f"}}"
        )

        # ── Log card ───────────────────────────────────────────────────
        self._log_card.setStyleSheet(
            f"QGroupBox {{"
            f"  background-color: {Colors.BG_PANEL};"
            f"  border: 1px solid {Colors.BORDER};"
            f"  border-radius: 16px;"
            f"  margin-top: 0px;"
            f"}}"
        )

        # Toolbar
        toolbar_style = (
            f"QWidget#log_toolbar {{"
            f"  background-color: {Colors.BG_PANEL};"
            f"  border-top-left-radius: 16px;"
            f"  border-top-right-radius: 16px;"
            f"}}"
        )
        self._log_card.findChild(QWidget, "log_toolbar")
        for child in self._log_card.findChildren(QWidget):
            if child.objectName() == "log_toolbar":
                child.setStyleSheet(toolbar_style)

        # Search input
        input_style = (
            f"QLineEdit {{"
            f"  background-color: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};"
            f"  border: 1px solid {Colors.BORDER}; border-radius: 7px;"
            f"  padding: 2px 10px; font-size: 12px;"
            f"  font-family: 'Inter', 'Segoe UI', sans-serif;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: #6366F1;"
            f"}}"
        )
        self._search_input.setStyleSheet(input_style)

        # Level filter dropdown
        combo_style = (
            f"QComboBox {{"
            f"  background-color: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};"
            f"  border: 1px solid {Colors.BORDER}; border-radius: 7px;"
            f"  padding: 2px 8px; font-size: 12px;"
            f"  font-family: 'Inter', 'Segoe UI', sans-serif;"
            f"}}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};"
            f"  border: 1px solid {Colors.BORDER}; selection-background-color: #6366F122;"
            f"}}"
        )
        self._level_filter.setStyleSheet(combo_style)

        # Auto-scroll toggle
        self._scroll_toggle_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {Colors.BG_ELEVATED}; color: {Colors.TEXT_MUTED};"
            f"  border: 1px solid {Colors.BORDER}; border-radius: 7px;"
            f"  font-size: 11px; font-weight: 600; padding: 0 10px;"
            f"  font-family: 'Inter', 'Segoe UI', sans-serif;"
            f"}}"
            f"QPushButton:checked {{"
            f"  background-color: #6366F118; color: #6366F1; border-color: #6366F1;"
            f"}}"
        )

        # Toolbar icon buttons (clear + download)
        icon_btn_style = (
            f"QPushButton {{"
            f"  background-color: transparent; color: {Colors.TEXT_MUTED};"
            f"  border: 1px solid {Colors.BORDER}; border-radius: 7px;"
            f"  font-size: 11px; font-weight: 600; padding: 0 10px;"
            f"  font-family: 'Inter', 'Segoe UI', sans-serif;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};"
            f"  border-color: {Colors.TEXT_MUTED};"
            f"}}"
        )
        self._clear_logs_btn.setStyleSheet(icon_btn_style)
        self._dl_btn.setStyleSheet(icon_btn_style)

        # Terminal console
        self._log_view.setStyleSheet(
            f"QPlainTextEdit {{"
            f"  background-color: #0A0C10; color: #E2E8F0;"
            f"  border: none;"
            f"  border-bottom-left-radius: 16px;"
            f"  border-bottom-right-radius: 16px;"
            f"  padding: 12px 14px;"
            f"  selection-background-color: #6366F144;"
            f"  font-family: 'Consolas', 'Cascadia Code', 'Fira Code', monospace;"
            f"}}"
        )

        # Propagate to child components
        self._summary.refresh_theme()
        self._exec_summary.refresh_theme()
        self._timeline.update()
