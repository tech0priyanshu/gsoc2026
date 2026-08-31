"""
gui/controllers/results_controller.py
-------------------------------------
Business-logic controller for the Results panel.

Collects execution outputs from Pipeline and Batch runs,
storing them in the ResultsState model.

Also manages NPY visualization scanning, rendering, and export.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

try:
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.models.results_state import (
    NpyVisualization,
    ResultsState,
    ResultItem,
)


class ResultsController(QObject):
    """
    Signals
    -------
    result_added(ResultItem)
    result_removed(result_id)
    results_cleared()
    visualization_ready(dict)
        Per-file visualization data: {path, metadata, png_bytes, error}
    all_visualizations_ready(str)
        result_id when all visualizations for a batch result are done
    scan_progress(int, int)
        (current, total) scan progress
    export_finished(str)
        Path to exported folder or zip
    """
    result_added = pyqtSignal(object)
    result_removed = pyqtSignal(str)
    results_cleared = pyqtSignal()
    visualization_ready = pyqtSignal(dict)
    all_visualizations_ready = pyqtSignal(str)
    scan_progress = pyqtSignal(int, int)
    export_finished = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = ResultsState()
        self._scanner = None
        self._exporter = None
        self._current_scan_result_id: Optional[str] = None
        self._current_visualizations: List[Dict] = []
        self._theme: str = "dark"  # Updated by MainWindow on theme change

    @property
    def theme(self) -> str:
        return self._theme

    @theme.setter
    def theme(self, value: str) -> None:
        self._theme = value

    # ------------------------------------------------------------------
    # Pipeline results
    # ------------------------------------------------------------------

    def add_pipeline_result(self, summary: str, result_dict: Optional[dict] = None) -> None:
        """Called when a pipeline execution successfully completes."""
        if result_dict is not None:
            try:
                full_output = json.dumps(result_dict, indent=2)
            except Exception:
                full_output = str(result_dict)
        else:
            full_output = summary
            
        item = ResultItem(
            name="Pipeline Execution",
            result_type="pipeline",
            status="COMPLETED",
            summary=summary,
            full_output=full_output,
        )
        self.state.add_result(item)
        self.result_added.emit(item)

    def add_pipeline_error(self, error_msg: str) -> None:
        """Called when a pipeline execution fails."""
        item = ResultItem(
            name="Pipeline Execution",
            result_type="pipeline",
            status="FAILED",
            summary="Pipeline execution failed.",
            full_output=f"Error occurred during pipeline execution:\n{error_msg}\n\nSuggested Resolution: Check the pipeline configuration and ensure all node parameters are correct.",
        )
        self.state.add_result(item)
        self.result_added.emit(item)

    # ------------------------------------------------------------------
    # Batch results
    # ------------------------------------------------------------------

    def add_batch_result(self, results_list: list, html_report_path: Optional[str] = None) -> None:
        """Called when a batch execution completes."""
        total = len(results_list)
        completed = sum(1 for r in results_list if r.get("status") == "COMPLETED")
        failed = sum(1 for r in results_list if r.get("status") == "FAILED")
        
        summary = f"Batch finished: {completed}/{total} completed, {failed} failed."
        
        output_lines = [summary, "", "Individual Job Results:"]

        # Collect data_dirs from completed jobs for visualization scanning
        data_dirs: List[str] = []
        for r in results_list:
            job_id = r.get("job_id", "unknown")
            status = r.get("status", "unknown")
            duration = r.get("duration")
            dur_str = f"{duration:.2f}s" if duration else "N/A"
            error = r.get("error", "")
            
            output_lines.append(f"- Job {job_id}: {status} ({dur_str})")
            if error:
                output_lines.append(f"  Error: {error}")

            # Collect data directories from completed jobs
            if status == "COMPLETED":
                data_dir = r.get("data_dir", "")
                if data_dir and os.path.isdir(data_dir):
                    data_dirs.append(data_dir)
                
        full_output = "\n".join(output_lines)

        status_str = "COMPLETED" if failed == 0 else "FAILED"
        
        item = ResultItem(
            name="Batch Execution",
            result_type="batch",
            status=status_str,
            summary=summary,
            full_output=full_output,
            data_dirs=data_dirs,
        )
        self.state.add_result(item)
        self.result_added.emit(item)

        # Auto-trigger NPY scanning for completed jobs
        if data_dirs:
            self.scan_result_dirs(data_dirs, item.id)

    def add_batch_error(self, error_msg: str) -> None:
        """Called when batch execution fails entirely before jobs can complete."""
        item = ResultItem(
            name="Batch Execution",
            result_type="batch",
            status="FAILED",
            summary="Batch execution failed.",
            full_output=f"Fatal error during batch execution:\n{error_msg}\n\nSuggested Resolution: Check logs for details or verify input data.",
        )
        self.state.add_result(item)
        self.result_added.emit(item)

    # ------------------------------------------------------------------
    # NPY Visualization Scanning
    # ------------------------------------------------------------------

    def scan_result_dirs(self, data_dirs: List[str], result_id: str) -> None:
        """
        Launch background scanner for .npy files in the given directories.
        
        Parameters
        ----------
        data_dirs : list[str]
            Directories to scan recursively for .npy files.
        result_id : str
            ID of the ResultItem to attach visualizations to.
        """
        from pyasl.gui.threads.npy_scanner_worker import NpyScannerWorker

        self._current_scan_result_id = result_id
        self._current_visualizations = []

        self._scanner = NpyScannerWorker(data_dirs, theme=self._theme)
        self._scanner.file_visualized.connect(self._on_file_visualized)
        self._scanner.scan_complete.connect(self._on_scan_complete)
        self._scanner.progress_update.connect(
            lambda cur, tot: self.scan_progress.emit(cur, tot)
        )
        self._scanner.start()

    def _on_file_visualized(self, data: Dict) -> None:
        """Handle a single file visualization result from the scanner."""
        self._current_visualizations.append(data)

        # Create NpyVisualization and attach to the result item
        result = self.state.get_result(self._current_scan_result_id)
        if result:
            viz = NpyVisualization(
                file_path=data["path"],
                metadata=data["metadata"],
                png_bytes=data.get("png_bytes"),
                error=data.get("error"),
            )
            result.visualizations.append(viz)

        self.visualization_ready.emit(data)

    def _on_scan_complete(self, all_results: List[Dict]) -> None:
        """Handle scan completion."""
        result_id = self._current_scan_result_id
        if result_id:
            self.all_visualizations_ready.emit(result_id)
        self._scanner = None

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_visualizations(self, result_id: str) -> None:
        """
        Export all visualizations for a result to PNG files.

        Saves to ``<first_data_dir>/visualizations/``.
        """
        result = self.state.get_result(result_id)
        if not result or not result.visualizations:
            return

        # Determine output directory
        if result.data_dirs:
            output_dir = result.data_dirs[0]
        else:
            output_dir = "."

        from pyasl.gui.threads.npy_scanner_worker import NpyExportWorker

        viz_data = [
            {
                "metadata": v.metadata,
                "png_bytes": v.png_bytes,
            }
            for v in result.visualizations
            if v.is_valid
        ]

        self._exporter = NpyExportWorker(
            viz_data, output_dir, create_zip=False
        )
        self._exporter.export_complete.connect(
            lambda path: self.export_finished.emit(path)
        )
        self._exporter.start()

    def download_all_zip(self, result_id: str) -> None:
        """
        Export all visualizations as PNGs and create a ZIP archive.
        """
        result = self.state.get_result(result_id)
        if not result or not result.visualizations:
            return

        if result.data_dirs:
            output_dir = result.data_dirs[0]
        else:
            output_dir = "."

        from pyasl.gui.threads.npy_scanner_worker import NpyExportWorker

        viz_data = [
            {
                "metadata": v.metadata,
                "png_bytes": v.png_bytes,
            }
            for v in result.visualizations
            if v.is_valid
        ]

        self._exporter = NpyExportWorker(
            viz_data, output_dir, create_zip=True
        )
        self._exporter.export_complete.connect(
            lambda path: self.export_finished.emit(path)
        )
        self._exporter.zip_complete.connect(
            lambda path: self.export_finished.emit(path)
        )
        self._exporter.start()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def remove_result(self, result_id: str) -> None:
        """Remove a result from the state."""
        self.state.remove_result(result_id)
        self.result_removed.emit(result_id)

    def clear_all(self) -> None:
        """Clear all results."""
        self.state.clear()
        self.results_cleared.emit()
