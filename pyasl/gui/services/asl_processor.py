"""
gui/services/asl_processor.py
------------------------------
Adapter between the ASL pipeline/batch system and the Result Window.

Responsibilities:
- Scan output directories for .npy files
- Load arrays and extract metadata
- Normalize pipeline/batch results into ``ProcessedResult``
- Capture errors, warnings, partial results
- Validate output schema

This service is the **only** place that touches raw ASL output.
The dashboard UI never calls ASL directly.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np

from pyasl.gui.models.result_data import (
    ComparisonPair,
    DatasetEntry,
    ProcessedResult,
    ResultMetadata,
)

logger = logging.getLogger(__name__)


class ASLProcessor:
    """
    Transforms raw ASL pipeline / batch output into normalised
    ``ProcessedResult`` objects.
    """

    # Well-known ASL output array names and their descriptions
    _KNOWN_OUTPUTS: Dict[str, str] = {
        "ImageDif": "Control–Label Difference Image",
        "Mat0": "M0 Magnetisation Map",
        "relCBF": "Relative CBF Map",
        "absCBF": "Absolute CBF Map (ml/100g/min)",
        "BrainMask": "Brain Mask (binary)",
        "cbf_map": "CBF Map",
        "mean_control": "Mean Control Image",
        "mean_label": "Mean Label Image",
        "perfusion": "Perfusion-Weighted Image",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_pipeline_result(
        self,
        summary: str,
        result_dict: Optional[Dict[str, Any]] = None,
        execution_log: Optional[List[Dict[str, Any]]] = None,
    ) -> ProcessedResult:
        """
        Normalise a pipeline execution result.

        Parameters
        ----------
        summary : str
            Human-readable summary text.
        result_dict : dict, optional
            Raw ``PipelineResult`` dictionary.
        execution_log : list, optional
            Node execution log entries.
        """
        meta = ResultMetadata(
            pipeline_name=result_dict.get("pipeline", "pipeline") if result_dict else "pipeline",
            pipeline_type="dag",
            asl_library="PyASL",
        )

        if result_dict:
            meta.processing_duration = result_dict.get("duration")
            meta.execution_log = execution_log or result_dict.get("execution_log", [])

            # Count nodes
            nodes = result_dict.get("nodes", {})
            if isinstance(nodes, dict):
                meta.node_count = len(nodes)
                meta.completed_nodes = sum(
                    1 for v in nodes.values()
                    if isinstance(v, dict) and v.get("status") == "success"
                )
                meta.failed_nodes = sum(
                    1 for v in nodes.values()
                    if isinstance(v, dict) and v.get("status") in ("failed", "error")
                )

        try:
            from pyasl._version import __version__
            meta.asl_version = __version__
        except ImportError:
            meta.asl_version = "unknown"

        result = ProcessedResult(
            name="Pipeline Result",
            processing_metadata=meta,
        )

        # If we have data directories from pipeline output, scan them
        if result_dict:
            data_dirs = self._extract_data_dirs(result_dict)
            if data_dirs:
                entries = self._scan_directories(data_dirs)
                result.entries = entries
                result.source_reference = data_dirs[0] if data_dirs else ""

        return result

    def process_batch_result(
        self,
        results_list: List[Dict[str, Any]],
        data_dirs: Optional[List[str]] = None,
    ) -> ProcessedResult:
        """
        Normalise a batch execution result.

        Parameters
        ----------
        results_list : list
            List of per-job result dictionaries.
        data_dirs : list, optional
            Directories containing output .npy files.
        """
        total = len(results_list)
        completed = sum(1 for r in results_list if r.get("status") == "COMPLETED")
        failed = sum(1 for r in results_list if r.get("status") == "FAILED")

        meta = ResultMetadata(
            pipeline_name="Batch Execution",
            pipeline_type="batch",
            asl_library="PyASL",
            node_count=total,
            completed_nodes=completed,
            failed_nodes=failed,
        )

        # Collect durations
        durations = [
            r.get("duration", 0) for r in results_list
            if r.get("duration") is not None
        ]
        if durations:
            meta.processing_duration = sum(durations)

        # Collect errors
        for r in results_list:
            err = r.get("error")
            if err:
                meta.errors.append(f"Job {r.get('job_id', '?')}: {err}")

        try:
            from pyasl._version import __version__
            meta.asl_version = __version__
        except ImportError:
            meta.asl_version = "unknown"

        # Scan data directories for .npy outputs
        entries: List[DatasetEntry] = []
        if data_dirs:
            entries = self._scan_directories(data_dirs)

        source = data_dirs[0] if data_dirs else ""

        # Build comparison pairs from job results
        comparisons = self._build_batch_comparisons(results_list)

        result = ProcessedResult(
            name="Batch Result",
            source_reference=source,
            entries=entries,
            processing_metadata=meta,
            comparisons=comparisons,
        )

        return result

    def load_result_from_directories(
        self, data_dirs: List[str], name: str = "Loaded Result"
    ) -> ProcessedResult:
        """
        Create a ProcessedResult by scanning directories for .npy files.

        Used when reopening a saved result without rerunning ASL.
        """
        entries = self._scan_directories(data_dirs)
        try:
            from pyasl._version import __version__
            version = __version__
        except ImportError:
            version = "unknown"

        return ProcessedResult(
            name=name,
            source_reference=data_dirs[0] if data_dirs else "",
            entries=entries,
            processing_metadata=ResultMetadata(
                asl_library="PyASL",
                asl_version=version,
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_directories(self, dirs: List[str]) -> List[DatasetEntry]:
        """Recursively scan directories for .npy files and load them."""
        entries: List[DatasetEntry] = []
        seen_paths: set = set()

        for directory in dirs:
            if not os.path.isdir(directory):
                logger.warning("Data directory does not exist: %s", directory)
                continue

            for root, _subdirs, files in os.walk(directory):
                for fname in sorted(files):
                    if not fname.lower().endswith(".npy"):
                        continue
                    fpath = os.path.join(root, fname)
                    if fpath in seen_paths:
                        continue
                    seen_paths.add(fpath)

                    entry = self._load_npy_entry(fpath)
                    entries.append(entry)

        return entries

    def _load_npy_entry(self, fpath: str) -> DatasetEntry:
        """Load a single .npy file into a DatasetEntry."""
        name = os.path.splitext(os.path.basename(fpath))[0]
        description = self._KNOWN_OUTPUTS.get(name, f"Output array: {name}")

        try:
            arr = np.load(fpath, allow_pickle=False)
            entry = DatasetEntry(
                name=name,
                file_path=fpath,
                shape=arr.shape,
                dtype=str(arr.dtype),
                ndim=arr.ndim,
                min_val=float(np.nanmin(arr)) if arr.size > 0 else None,
                max_val=float(np.nanmax(arr)) if arr.size > 0 else None,
                mean_val=float(np.nanmean(arr)) if arr.size > 0 else None,
                std_val=float(np.nanstd(arr)) if arr.size > 0 else None,
                size=int(arr.size),
                description=description,
                has_data=True,
                error=None,
            )
            # Store raw data reference for in-memory analytics
            entry.raw_data = arr
            return entry

        except Exception as exc:
            logger.error("Failed to load %s: %s", fpath, exc)
            return DatasetEntry(
                name=name,
                file_path=fpath,
                description=description,
                has_data=False,
                error=str(exc),
            )

    def _extract_data_dirs(self, result_dict: Dict[str, Any]) -> List[str]:
        """Extract data directories from a pipeline result dict."""
        dirs: List[str] = []
        nodes = result_dict.get("nodes", {})
        if isinstance(nodes, dict):
            for _nid, node_result in nodes.items():
                if not isinstance(node_result, dict):
                    continue
                outputs = node_result.get("outputs", {})
                if isinstance(outputs, dict):
                    for key in ("savedir", "output_dir", "data_dir"):
                        val = outputs.get(key)
                        if val and isinstance(val, str) and os.path.isdir(val):
                            dirs.append(val)
        return dirs

    def _build_batch_comparisons(
        self, results_list: List[Dict[str, Any]]
    ) -> List[ComparisonPair]:
        """Build comparison pairs from batch job configurations."""
        comparisons: List[ComparisonPair] = []

        for r in results_list:
            job_id = r.get("job_id", "unknown")
            status = r.get("status", "unknown")
            duration = r.get("duration")

            comparisons.append(ComparisonPair(
                field_name=f"Job {job_id} — Status",
                original_value="PENDING",
                processed_value=status,
                difference=status,
                has_changed=(status != "PENDING"),
            ))
            if duration is not None:
                comparisons.append(ComparisonPair(
                    field_name=f"Job {job_id} — Duration",
                    original_value=None,
                    processed_value=f"{duration:.2f}s",
                    difference=f"{duration:.2f}s",
                    has_changed=True,
                ))

        return comparisons
