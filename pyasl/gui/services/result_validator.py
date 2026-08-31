"""
gui/services/result_validator.py
---------------------------------
Validates ``ProcessedResult`` objects before storage or display.

Pure Python — no Qt dependency.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from pyasl.gui.models.result_data import DatasetEntry, ProcessedResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single validation finding."""
    severity: str = "error"   # "error" | "warning" | "info"
    field: str = ""
    message: str = ""


@dataclass
class ValidationResult:
    """Outcome of validating a ``ProcessedResult``."""
    is_valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)

    def add_error(self, field: str, message: str) -> None:
        self.issues.append(ValidationIssue("error", field, message))
        self.is_valid = False

    def add_warning(self, field: str, message: str) -> None:
        self.issues.append(ValidationIssue("warning", field, message))

    def add_info(self, field: str, message: str) -> None:
        self.issues.append(ValidationIssue("info", field, message))

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


class ResultValidator:
    """Validates ProcessedResult objects."""

    def validate(self, result: ProcessedResult) -> ValidationResult:
        """
        Validate a ProcessedResult.

        Checks:
        - result_id is present
        - name is non-empty
        - entries have valid schemas
        - numerical values are finite
        - no duplicate entry names
        """
        vr = ValidationResult()

        # ID
        if not result.result_id:
            vr.add_error("result_id", "Result ID is missing.")

        # Name
        if not result.name or not result.name.strip():
            vr.add_warning("name", "Result name is empty.")

        # Entries
        if not result.entries:
            vr.add_info("entries", "Result contains no dataset entries.")

        seen_names: set = set()
        for i, entry in enumerate(result.entries):
            self._validate_entry(entry, i, vr, seen_names)

        # Metadata
        meta = result.processing_metadata
        if meta.failed_nodes > 0:
            vr.add_warning(
                "processing_metadata",
                f"{meta.failed_nodes} node(s) failed during processing.",
            )

        return vr

    def _validate_entry(
        self,
        entry: DatasetEntry,
        index: int,
        vr: ValidationResult,
        seen_names: set,
    ) -> None:
        """Validate a single DatasetEntry."""
        prefix = f"entries[{index}]"

        # Name
        if not entry.name:
            vr.add_error(f"{prefix}.name", "Entry name is missing.")

        # Duplicate check
        if entry.name in seen_names:
            vr.add_warning(
                f"{prefix}.name",
                f"Duplicate entry name: '{entry.name}'.",
            )
        seen_names.add(entry.name)

        # Error state
        if entry.error:
            vr.add_warning(
                f"{prefix}.error",
                f"Entry '{entry.name}' has error: {entry.error}",
            )
            return  # Skip further checks for errored entries

        # Dtype
        if entry.dtype == "unknown" and entry.has_data:
            vr.add_warning(f"{prefix}.dtype", f"Entry '{entry.name}' has unknown dtype.")

        # Shape
        if entry.has_data and entry.shape is None:
            vr.add_warning(f"{prefix}.shape", f"Entry '{entry.name}' has no shape info.")

        # NaN/Inf checks for statistics
        if entry.min_val is not None:
            import math
            if math.isinf(entry.min_val) or math.isnan(entry.min_val):
                vr.add_warning(
                    f"{prefix}.min_val",
                    f"Entry '{entry.name}' min is not finite: {entry.min_val}",
                )
        if entry.max_val is not None:
            import math
            if math.isinf(entry.max_val) or math.isnan(entry.max_val):
                vr.add_warning(
                    f"{prefix}.max_val",
                    f"Entry '{entry.name}' max is not finite: {entry.max_val}",
                )

    def validate_for_save(self, result: ProcessedResult) -> ValidationResult:
        """Extra validation before persisting (stricter)."""
        vr = self.validate(result)

        if not result.result_id:
            vr.add_error("result_id", "Cannot save a result without an ID.")

        if not result.created_at:
            vr.add_error("created_at", "Cannot save without a creation timestamp.")

        return vr
