"""
gui/views/batch_panel_view.py
-------------------------------
Batch Mode tab view.

Presents the job queue table, progress bar with ETA, BIDS bulk import,
and action buttons.
All business logic is delegated to ``BatchController``.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
from typing import Optional

try:
    from PyQt6.QtCore import Qt  # type: ignore
    from PyQt6.QtGui import QColor, QGuiApplication  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
        QTableWidget, QTableWidgetItem, QHeaderView,
        QFileDialog, QMessageBox, QLabel, QSpinBox,
        QGroupBox, QProgressBar, QMenu,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.controllers.batch_controller import BatchController
from pyasl.gui.constants import Colors, BATCH_COLUMNS, STATUS_TABLE_COLORS
from pyasl.gui.error_map import format_human_error


class BatchPanelView(QWidget):
    """
    Batch Mode tab widget.

    Receives a ``BatchController`` and wires all UI actions to it.
    """

    def __init__(self, controller: BatchController, parent=None):
        super().__init__(parent)
        self._ctrl = controller
        self._batch_start_time: Optional[float] = None
        self._setup_ui()
        self._wire_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header
        hdr = QLabel("Batch Processing")
        hdr.setProperty("heading", "true")
        root.addWidget(hdr)

        sub = QLabel("Queue multiple datasets and process them in parallel.")
        sub.setProperty("muted", "true")
        root.addWidget(sub)

        # Controls row
        ctrl = QHBoxLayout()

        add_btn = QPushButton("＋ Add Job")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._on_add_job)

        bids_btn = QPushButton("📁 Import BIDS Dataset")
        bids_btn.setFixedHeight(32)
        bids_btn.clicked.connect(self._on_import_bids)

        remove_btn = QPushButton("✖ Remove Selected")
        remove_btn.setProperty("flat", "true")
        remove_btn.setFixedHeight(32)
        remove_btn.clicked.connect(self._on_remove_selected)

        clear_btn = QPushButton(" Clear All")
        clear_btn.setProperty("danger", "true")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._ctrl.clear)

        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 16)
        self._workers_spin.setValue(2)
        self._workers_spin.setPrefix("Workers: ")
        self._workers_spin.setFixedSize(138, 38)

        self._run_btn = QPushButton("Run Batch")
        self._run_btn.setProperty("success", "true")
        self._run_btn.setFixedHeight(32)
        self._run_btn.clicked.connect(self._on_run)

        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setProperty("danger", "true")
        self._abort_btn.setFixedHeight(32)
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._on_abort)

        for w in [add_btn, bids_btn, remove_btn, clear_btn]:
            ctrl.addWidget(w)
        ctrl.addStretch()
        ctrl.addWidget(self._workers_spin)
        ctrl.addWidget(self._run_btn)
        ctrl.addWidget(self._abort_btn)
        root.addLayout(ctrl)

        # Table
        self._table = QTableWidget(0, len(BATCH_COLUMNS))
        self._table.setHorizontalHeaderLabels(BATCH_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch,
        )
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch,
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows,
        )
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        root.addWidget(self._table, stretch=1)

        # Progress summary with ETA (Priority 5C)
        prog_grp = QGroupBox("Progress")
        prog_lay = QHBoxLayout(prog_grp)
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setFormat("No jobs running")
        self._summary_lbl = QLabel("No jobs queued")
        self._summary_lbl.setProperty("muted", "true")
        prog_lay.addWidget(self._progress)
        prog_lay.addWidget(self._summary_lbl)
        root.addWidget(prog_grp)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self):
        self._ctrl.job_added.connect(self._on_job_added)
        self._ctrl.jobs_cleared.connect(self._on_jobs_cleared)
        self._ctrl.job_status_changed.connect(self._on_job_status_changed)
        self._ctrl.batch_started.connect(self._on_batch_started)
        self._ctrl.batch_completed.connect(self._on_batch_completed)
        self._ctrl.error.connect(self._on_batch_error)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.customContextMenuRequested.connect(
            self._on_table_context_menu
        )

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------

    def _on_add_job(self):
        data_dir = QFileDialog.getExistingDirectory(
            self, "Select Data Directory",
        )
        if not data_dir:
            return
        config_path, _ = QFileDialog.getOpenFileName(
            self, "Select Pipeline Config", "",
            "YAML Files (*.yaml *.yml)",
        )
        if not config_path:
            return
        self._ctrl.add_job(data_dir, config_path)

    def _on_import_bids(self):
        """Bulk import a BIDS dataset with sub-* subject directories (Priority 5D)."""
        dataset_root = QFileDialog.getExistingDirectory(
            self, "Select BIDS Dataset Root Directory",
        )
        if not dataset_root:
            return

        config_path, _ = QFileDialog.getOpenFileName(
            self, "Select Shared Pipeline Config for BIDS Import", "",
            "YAML Files (*.yaml *.yml)",
        )
        if not config_path:
            return

        # Scan for sub-* directories
        sub_dirs = sorted([
            d for d in glob.glob(os.path.join(dataset_root, "sub-*"))
            if os.path.isdir(d)
        ])

        if not sub_dirs:
            QMessageBox.warning(
                self, "No Subjects Found",
                f"No 'sub-*' subject directories found in:\n{dataset_root}",
            )
            return

        reply = QMessageBox.question(
            self, "Confirm BIDS Import",
            f"Found {len(sub_dirs)} subject(s) in dataset root:\n"
            f"{dataset_root}\n\nAdd all {len(sub_dirs)} subjects to batch queue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            for s_dir in sub_dirs:
                self._ctrl.add_job(s_dir, config_path)

    def _on_remove_selected(self):
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        job_ids = []
        for r in rows:
            item = self._table.item(r, 0)
            if item:
                job_ids.append(item.text())
            self._table.removeRow(r)
        if job_ids:
            self._ctrl.remove_jobs(job_ids)
        self._update_summary()

    def _on_run(self):
        self._batch_start_time = time.time()
        self._ctrl.run(max_workers=self._workers_spin.value())

    def _on_abort(self):
        self._ctrl.abort()
        self._abort_btn.setEnabled(False)
        self._run_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Context menu for table rows
    # ------------------------------------------------------------------

    def _on_table_context_menu(self, pos):
        """Show a context menu with path actions for the clicked row."""
        row = self._table.rowAt(pos.y())
        if row < 0:
            return

        job_id_item = self._table.item(row, 0)
        data_dir_item = self._table.item(row, 2)
        config_item = self._table.item(row, 3)
        if not job_id_item:
            return

        job_id = job_id_item.text()
        data_dir = data_dir_item.text() if data_dir_item else ""
        config = config_item.text() if config_item else ""

        menu = QMenu(self)

        copy_data = menu.addAction("📋  Copy Data Folder Path")
        copy_config = menu.addAction("📋  Copy Config Path")
        menu.addSeparator()
        open_folder = menu.addAction("📂  Open Data Folder in Explorer")
        menu.addSeparator()
        change_data = menu.addAction("🔄  Change Data Folder…")
        change_config = menu.addAction("🔄  Change Config File…")

        job = self._ctrl.state.get_job(job_id)
        show_error = None
        if job and job.status == "FAILED" and job.error:
            menu.addSeparator()
            show_error = menu.addAction("❌  Show Error Details")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))

        if chosen == copy_data:
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(data_dir)
        elif chosen == copy_config:
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(config)
        elif chosen == open_folder:
            if os.path.isdir(data_dir):
                if sys.platform == "win32":
                    os.startfile(data_dir)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", data_dir])
                else:
                    subprocess.Popen(["xdg-open", data_dir])
        elif chosen == change_data:
            new_dir = QFileDialog.getExistingDirectory(
                self, "Select New Data Directory", data_dir,
            )
            if new_dir:
                self._update_job_data_dir(row, job_id, new_dir)
        elif chosen == change_config:
            new_cfg, _ = QFileDialog.getOpenFileName(
                self, "Select New Config", "",
                "YAML Files (*.yaml *.yml)",
            )
            if new_cfg:
                self._update_job_config(row, job_id, new_cfg)
        elif show_error and chosen == show_error:
            self._show_error_details(job_id)

    def _update_job_data_dir(self, row: int, job_id: str, new_dir: str):
        job = self._ctrl.state.get_job(job_id)
        if job:
            job.data_dir = new_dir
            job.label = os.path.basename(new_dir)
            self._table.item(row, 1).setText(job.label)
            item = self._table.item(row, 2)
            item.setText(new_dir)
            item.setToolTip(new_dir)

    def _update_job_config(self, row: int, job_id: str, new_cfg: str):
        job = self._ctrl.state.get_job(job_id)
        if job:
            job.config_path = new_cfg
            item = self._table.item(row, 3)
            item.setText(os.path.basename(new_cfg))
            item.setToolTip(new_cfg)

    # ------------------------------------------------------------------
    # Controller signal handlers
    # ------------------------------------------------------------------

    def _on_job_added(self, job):
        row = self._table.rowCount()
        self._table.insertRow(row)
        cells = job.to_table_row()
        for col, val in enumerate(cells):
            item = QTableWidgetItem(val)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 2:
                item.setToolTip(job.data_dir)
            elif col == 3:
                item.setToolTip(job.config_path)
            self._table.setItem(row, col, item)
        self._apply_status_color(row, job.status)
        self._update_summary()

    def _on_jobs_cleared(self):
        self._table.setRowCount(0)
        self._batch_start_time = None
        self._update_summary()

    def _on_job_status_changed(self, job_id: str, status: str):
        for r in range(self._table.rowCount()):
            if self._table.item(r, 0).text() == job_id:
                self._table.item(r, 5).setText(status)
                self._apply_status_color(r, status)
                break
        self._update_summary()

    def _on_batch_started(self):
        self._batch_start_time = time.time()
        self._run_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)

    def _on_batch_completed(self, results: list):
        for res in results:
            jid = res["job_id"]
            dur = res.get("duration")
            for r in range(self._table.rowCount()):
                if self._table.item(r, 0).text() == jid:
                    dur_str = f"{dur:.2f}s" if dur else "—"
                    self._table.item(r, 6).setText(dur_str)
                    break
        self._run_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        QMessageBox.information(
            self, "Batch Complete",
            f"All {len(results)} jobs finished.",
        )

    def _on_batch_error(self, msg: str):
        self._run_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        # Priority 5E: Human-readable error message formatting
        human_msg = format_human_error(msg)
        QMessageBox.critical(self, "Batch Error", human_msg)

    def _on_cell_double_clicked(self, row: int, col: int):
        job_id = self._table.item(row, 0).text()
        job = self._ctrl.state.get_job(job_id)

        if col == 2 and job and os.path.isdir(job.data_dir):
            if sys.platform == "win32":
                os.startfile(job.data_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", job.data_dir])
            else:
                subprocess.Popen(["xdg-open", job.data_dir])
            return

        if job and job.status == "FAILED" and job.error:
            self._show_error_details(job_id)

    def _show_error_details(self, job_id: str):
        """Show a detailed human-readable error dialog for a failed job (Priority 5E)."""
        job = self._ctrl.state.get_job(job_id)
        if not job:
            return
        tb = job.traceback or ""
        human_guidance = format_human_error(job.error or "Unknown error")

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("Job Error Details")
        msg_box.setText(f"Job '{job_id}' failed.")
        msg_box.setInformativeText(human_guidance)
        msg_box.setDetailedText(tb if tb else "No traceback available.")
        msg_box.setStyleSheet("QPlainTextEdit { min-width: 600px; min-height: 300px; }")
        msg_box.exec()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_status_color(self, row: int, status: str):
        bg_hex, fg_hex = STATUS_TABLE_COLORS.get(
            status, (Colors.BG_PANEL, Colors.TEXT_PRIMARY),
        )
        bg = QColor(bg_hex)
        fg = QColor(fg_hex)
        for col in range(self._table.columnCount()):
            item = self._table.item(row, col)
            if item:
                item.setBackground(bg)
                item.setForeground(fg)

    def _update_summary(self):
        summary = self._ctrl.state.progress_summary()
        completed = summary["completed"]
        total = summary["total"]
        remaining = summary["pending"]
        done = summary["done"]

        self._summary_lbl.setText(
            f"{total} jobs  |  "
            f"✅ {completed}  "
            f"❌ {summary['failed']}  "
            f"⏳ {remaining}"
        )
        self._progress.setMaximum(max(total, 1))
        self._progress.setValue(done)

        # Priority 5C: ETA Calculation
        if self._batch_start_time and completed > 0 and remaining > 0:
            elapsed = time.time() - self._batch_start_time
            avg_dur = elapsed / completed
            eta_sec = int(avg_dur * remaining)
            if eta_sec >= 60:
                eta_str = f"{eta_sec // 60}m {eta_sec % 60}s"
            else:
                eta_str = f"{eta_sec}s"
            self._progress.setFormat(f"Subject {completed}/{total} — ETA: ~{eta_str}")
        elif total > 0 and done == total:
            self._progress.setFormat(f"Completed {total}/{total}")
        else:
            self._progress.setFormat(f"Subject {completed}/{total}" if total > 0 else "No jobs running")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme_styles(self):
        """Re-apply status colors on all table rows after a theme change."""
        for r in range(self._table.rowCount()):
            status_item = self._table.item(r, 5)
            if status_item:
                self._apply_status_color(r, status_item.text())
