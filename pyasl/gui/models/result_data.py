"""
gui/models/result_data.py
--------------------------
Canonical result data model for processed ASL results.

This module defines the **immutable** data structures that represent
the single source of truth for a processed result.  UI state (view mode,
filters, search, etc.) is kept in a separate module
(``result_ui_state.py``) and MUST NOT mutate these objects.

Architecture
~~~~~~~~~~~~
::

    ASL Processor  →  ProcessedResult  →  ResultService  →  Dashboard
                                        ↘  ResultRepository (persistence)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# DatasetEntry — one output array/artifact from ASL processing
# ---------------------------------------------------------------------------

@dataclass
class DatasetEntry:
    """
    A single output artifact (e.g. a .npy array) from ASL processing.

    Attributes
    ----------
    name : str
        Human-readable name (e.g. ``"absCBF"``, ``"BrainMask"``).
    file_path : str
        Absolute path to the source file on disk.
    shape : tuple[int, ...] | None
        Array shape, e.g. ``(128, 128, 20)``.
    dtype : str
        Numpy dtype string (e.g. ``"float64"``).
    ndim : int
        Number of dimensions.
    min_val : float | None
        Minimum value in the array.
    max_val : float | None
        Maximum value in the array.
    mean_val : float | None
        Mean value.
    std_val : float | None
        Standard deviation.
    size : int
        Total number of elements.
    description : str
        Auto-generated description.
    metadata : dict
        Arbitrary key-value metadata.
    has_data : bool
        Whether the raw data is available/loaded.
    error : str | None
        Error message if loading failed.
    """

    name: str
    file_path: str = ""
    shape: Optional[Tuple[int, ...]] = None
    dtype: str = "unknown"
    ndim: int = 0
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    mean_val: Optional[float] = None
    std_val: Optional[float] = None
    size: int = 0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    has_data: bool = True
    error: Optional[str] = None

    # ── Raw data (not serialized) ──
    # Kept as a transient reference; not included in to_dict()
    _raw_data: Any = field(default=None, repr=False, compare=False)

    @property
    def raw_data(self) -> Any:
        return self._raw_data

    @raw_data.setter
    def raw_data(self, value: Any) -> None:
        object.__setattr__(self, "_raw_data", value)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dictionary (excludes raw data)."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "shape": list(self.shape) if self.shape else None,
            "dtype": self.dtype,
            "ndim": self.ndim,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "mean_val": self.mean_val,
            "std_val": self.std_val,
            "size": self.size,
            "description": self.description,
            "metadata": self.metadata,
            "has_data": self.has_data,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetEntry":
        shape = tuple(d["shape"]) if d.get("shape") else None
        return cls(
            name=d.get("name", ""),
            file_path=d.get("file_path", ""),
            shape=shape,
            dtype=d.get("dtype", "unknown"),
            ndim=d.get("ndim", 0),
            min_val=d.get("min_val"),
            max_val=d.get("max_val"),
            mean_val=d.get("mean_val"),
            std_val=d.get("std_val"),
            size=d.get("size", 0),
            description=d.get("description", ""),
            metadata=d.get("metadata", {}),
            has_data=d.get("has_data", False),
            error=d.get("error"),
        )


# ---------------------------------------------------------------------------
# ResultMetadata — processing provenance
# ---------------------------------------------------------------------------

@dataclass
class ResultMetadata:
    """Processing provenance and configuration information."""

    pipeline_name: str = ""
    pipeline_type: str = ""          # "dag" | "legacy" | "batch"
    asl_library: str = "PyASL"
    asl_version: str = ""
    processing_duration: Optional[float] = None  # seconds
    config_path: str = ""
    config_yaml: str = ""
    execution_log: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    node_count: int = 0
    completed_nodes: int = 0
    failed_nodes: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_name": self.pipeline_name,
            "pipeline_type": self.pipeline_type,
            "asl_library": self.asl_library,
            "asl_version": self.asl_version,
            "processing_duration": self.processing_duration,
            "config_path": self.config_path,
            "config_yaml": self.config_yaml,
            "execution_log": self.execution_log,
            "warnings": self.warnings,
            "errors": self.errors,
            "node_count": self.node_count,
            "completed_nodes": self.completed_nodes,
            "failed_nodes": self.failed_nodes,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResultMetadata":
        return cls(
            pipeline_name=d.get("pipeline_name", ""),
            pipeline_type=d.get("pipeline_type", ""),
            asl_library=d.get("asl_library", "PyASL"),
            asl_version=d.get("asl_version", ""),
            processing_duration=d.get("processing_duration"),
            config_path=d.get("config_path", ""),
            config_yaml=d.get("config_yaml", ""),
            execution_log=d.get("execution_log", []),
            warnings=d.get("warnings", []),
            errors=d.get("errors", []),
            node_count=d.get("node_count", 0),
            completed_nodes=d.get("completed_nodes", 0),
            failed_nodes=d.get("failed_nodes", 0),
            extra=d.get("extra", {}),
        )


# ---------------------------------------------------------------------------
# ComparisonPair — original ↔ processed mapping
# ---------------------------------------------------------------------------

@dataclass
class ComparisonPair:
    """Maps an original input property to its processed counterpart."""

    field_name: str
    original_value: Any = None
    processed_value: Any = None
    difference: Optional[str] = None  # "+4", "Changed", "No change"
    has_changed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "original_value": _safe_serialize(self.original_value),
            "processed_value": _safe_serialize(self.processed_value),
            "difference": self.difference,
            "has_changed": self.has_changed,
        }


# ---------------------------------------------------------------------------
# ProcessedResult — the canonical result object
# ---------------------------------------------------------------------------

@dataclass
class ProcessedResult:
    """
    Immutable canonical representation of a processed ASL result.

    This is the **single source of truth**.  UI state, filters, search
    queries, visualization config — none of those live here.
    """

    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Result"
    source_reference: str = ""          # e.g. data directory path
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Datasets — the actual processed outputs
    entries: List[DatasetEntry] = field(default_factory=list)

    # Processing provenance
    processing_metadata: ResultMetadata = field(default_factory=ResultMetadata)

    # Original ↔ processed comparison pairs
    comparisons: List[ComparisonPair] = field(default_factory=list)

    # Input schema summary (config keys, parameter names, etc.)
    input_schema: Dict[str, Any] = field(default_factory=dict)

    # Output schema summary
    output_schema: Dict[str, Any] = field(default_factory=dict)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def has_errors(self) -> bool:
        return bool(self.processing_metadata.errors) or any(
            e.error for e in self.entries
        )

    @property
    def has_warnings(self) -> bool:
        return bool(self.processing_metadata.warnings)

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def get_entry(self, name: str) -> Optional[DatasetEntry]:
        """Find a dataset entry by name."""
        for e in self.entries:
            if e.name == name:
                return e
        return None

    def get_numerical_entries(self) -> List[DatasetEntry]:
        """Return entries with numerical data."""
        return [
            e for e in self.entries
            if e.has_data and e.dtype in (
                "float32", "float64", "int32", "int64",
                "uint8", "uint16", "uint32", "int8", "int16",
            )
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Full serialization to JSON-safe dict."""
        return {
            "result_id": self.result_id,
            "name": self.name,
            "source_reference": self.source_reference,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entries": [e.to_dict() for e in self.entries],
            "processing_metadata": self.processing_metadata.to_dict(),
            "comparisons": [c.to_dict() for c in self.comparisons],
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProcessedResult":
        entries = [DatasetEntry.from_dict(e) for e in d.get("entries", [])]
        meta = ResultMetadata.from_dict(d.get("processing_metadata", {}))
        comparisons = []
        for c in d.get("comparisons", []):
            comparisons.append(ComparisonPair(
                field_name=c.get("field_name", ""),
                original_value=c.get("original_value"),
                processed_value=c.get("processed_value"),
                difference=c.get("difference"),
                has_changed=c.get("has_changed", False),
            ))
        return cls(
            result_id=d.get("result_id", str(uuid.uuid4())),
            name=d.get("name", "Untitled Result"),
            source_reference=d.get("source_reference", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            entries=entries,
            processing_metadata=meta,
            comparisons=comparisons,
            input_schema=d.get("input_schema", {}),
            output_schema=d.get("output_schema", {}),
        )


# ---------------------------------------------------------------------------
# ResultSummary — lightweight listing item
# ---------------------------------------------------------------------------

@dataclass
class ResultSummary:
    """Lightweight summary for result history listing."""

    result_id: str = ""
    name: str = ""
    source_reference: str = ""
    created_at: str = ""
    entry_count: int = 0
    asl_version: str = ""
    has_errors: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "name": self.name,
            "source_reference": self.source_reference,
            "created_at": self.created_at,
            "entry_count": self.entry_count,
            "asl_version": self.asl_version,
            "has_errors": self.has_errors,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_serialize(value: Any) -> Any:
    """Convert a value to a JSON-safe type."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v) for k, v in value.items()}
    return str(value)
