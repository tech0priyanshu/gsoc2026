"""
gui/services/analytics_service.py
-----------------------------------
Pure computation service for analytics, aggregation, and chart data
preparation.  No Qt dependency.

All calculations are deterministic and memoizable.
"""
from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from pyasl.gui.models.result_data import DatasetEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chart data structures
# ---------------------------------------------------------------------------

@dataclass
class ChartDataPoint:
    label: str = ""
    value: float = 0.0
    percentage: float = 0.0
    color: str = ""


@dataclass
class ChartData:
    """Generic chart data container."""
    chart_type: str = ""
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    points: List[ChartDataPoint] = field(default_factory=list)
    series: Dict[str, List[float]] = field(default_factory=dict)
    x_values: List[Any] = field(default_factory=list)
    y_values: List[Any] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    matrix: Optional[np.ndarray] = None
    error_message: str = ""
    is_valid: bool = True


# ---------------------------------------------------------------------------
# AnalyticsService
# ---------------------------------------------------------------------------

class AnalyticsService:
    """
    Computes summaries, aggregations, and chart data from
    ``DatasetEntry`` lists.
    """

    # Default chart color palette — distinguishable, accessible
    CHART_COLORS = [
        "#830085",  # Brand purple
        "#FE565D",  # Brand coral
        "#22c55e",  # Green
        "#3b82f6",  # Blue
        "#f59e0b",  # Amber
        "#8b5cf6",  # Violet
        "#06b6d4",  # Cyan
        "#ec4899",  # Pink
        "#84cc16",  # Lime
        "#f97316",  # Orange
        "#6366f1",  # Indigo
        "#14b8a6",  # Teal
    ]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def compute_summary(self, entries: List[DatasetEntry]) -> Dict[str, Any]:
        """
        Compute dynamic summary metrics from dataset entries.

        Returns a dict of labelled metrics.  Never hard-codes metrics
        that may not exist.
        """
        if not entries:
            return {"Total Records": 0}

        summary: Dict[str, Any] = {
            "Total Records": len(entries),
        }

        # Aggregate numerical stats across all entries
        valid = [e for e in entries if e.has_data and e.error is None]
        errored = [e for e in entries if e.error is not None]

        if valid:
            summary["Valid Arrays"] = len(valid)

        if errored:
            summary["Errored"] = len(errored)

        # Shape distribution
        shapes = [str(e.shape) for e in valid if e.shape is not None]
        unique_shapes = set(shapes)
        if unique_shapes:
            summary["Unique Shapes"] = len(unique_shapes)

        # Dtype distribution
        dtypes = [e.dtype for e in valid if e.dtype != "unknown"]
        unique_dtypes = set(dtypes)
        if unique_dtypes:
            summary["Data Types"] = len(unique_dtypes)

        # Numerical stats
        min_vals = [e.min_val for e in valid if e.min_val is not None and math.isfinite(e.min_val)]
        max_vals = [e.max_val for e in valid if e.max_val is not None and math.isfinite(e.max_val)]
        mean_vals = [e.mean_val for e in valid if e.mean_val is not None and math.isfinite(e.mean_val)]

        if min_vals:
            summary["Global Min"] = round(min(min_vals), 4)
        if max_vals:
            summary["Global Max"] = round(max(max_vals), 4)
        if mean_vals:
            summary["Average Mean"] = round(sum(mean_vals) / len(mean_vals), 4)

        # Total elements
        total_size = sum(e.size for e in valid)
        if total_size > 0:
            if total_size > 1_000_000:
                summary["Total Elements"] = f"{total_size / 1_000_000:.1f}M"
            elif total_size > 1_000:
                summary["Total Elements"] = f"{total_size / 1_000:.1f}K"
            else:
                summary["Total Elements"] = total_size

        return summary

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def compute_aggregation(
        self,
        entries: List[DatasetEntry],
        field_name: str,
        agg_type: str = "mean",
    ) -> Optional[float]:
        """Compute a single aggregation over a field."""
        values = self._extract_field_values(entries, field_name)
        if not values:
            return None

        if agg_type == "count":
            return float(len(values))
        elif agg_type == "sum":
            return sum(values)
        elif agg_type == "mean":
            return sum(values) / len(values)
        elif agg_type == "min":
            return min(values)
        elif agg_type == "max":
            return max(values)
        elif agg_type == "std":
            if len(values) < 2:
                return 0.0
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            return math.sqrt(variance)
        return None

    # ------------------------------------------------------------------
    # Chart data preparation
    # ------------------------------------------------------------------

    def prepare_pie_data(
        self,
        entries: List[DatasetEntry],
        category_field: str = "name",
        measure_field: str = "mean_val",
        aggregation: str = "count",
        group_small: bool = True,
        threshold_pct: float = 2.0,
    ) -> ChartData:
        """Prepare data for a pie chart."""
        if not entries:
            return ChartData(
                chart_type="pie",
                error_message="No data available for pie chart.",
                is_valid=False,
            )

        # Build category → value mapping
        cat_values: Dict[str, float] = defaultdict(float)

        for entry in entries:
            cat = self._get_entry_field(entry, category_field) or "Unknown"
            cat = str(cat)

            if aggregation == "count":
                cat_values[cat] += 1.0
            else:
                val = self._get_entry_field(entry, measure_field)
                if val is not None and isinstance(val, (int, float)) and math.isfinite(val):
                    if aggregation == "sum":
                        cat_values[cat] += val
                    elif aggregation == "mean":
                        # For mean, we accumulate and count
                        cat_values[cat] += val
                    elif aggregation == "max":
                        cat_values[cat] = max(cat_values[cat], val)
                    elif aggregation == "min":
                        if cat not in cat_values:
                            cat_values[cat] = val
                        else:
                            cat_values[cat] = min(cat_values[cat], val)

        if not cat_values:
            return ChartData(
                chart_type="pie",
                error_message="No valid data for pie chart.",
                is_valid=False,
            )

        total = sum(cat_values.values())
        if total == 0:
            return ChartData(
                chart_type="pie",
                error_message="All values are zero.",
                is_valid=False,
            )

        # Sort by value descending
        sorted_cats = sorted(cat_values.items(), key=lambda x: x[1], reverse=True)

        # Group small categories
        points: List[ChartDataPoint] = []
        other_value = 0.0

        for i, (cat, val) in enumerate(sorted_cats):
            pct = (val / total) * 100
            if group_small and pct < threshold_pct and len(sorted_cats) > 6:
                other_value += val
            else:
                points.append(ChartDataPoint(
                    label=cat,
                    value=val,
                    percentage=round(pct, 1),
                    color=self.CHART_COLORS[i % len(self.CHART_COLORS)],
                ))

        if other_value > 0:
            pct = (other_value / total) * 100
            points.append(ChartDataPoint(
                label="Other",
                value=other_value,
                percentage=round(pct, 1),
                color="#94a3b8",
            ))

        return ChartData(
            chart_type="pie",
            title=f"{category_field} — {aggregation}",
            points=points,
            is_valid=True,
        )

    def prepare_bar_data(
        self,
        entries: List[DatasetEntry],
        x_field: str = "name",
        y_field: str = "mean_val",
        group_field: str = "",
    ) -> ChartData:
        """Prepare data for a bar chart."""
        if not entries:
            return ChartData(chart_type="bar", error_message="No data.", is_valid=False)

        x_values = []
        y_values = []

        for entry in entries:
            x = self._get_entry_field(entry, x_field)
            y = self._get_entry_field(entry, y_field)
            if x is not None and y is not None:
                x_values.append(str(x))
                y_values.append(float(y) if isinstance(y, (int, float)) and math.isfinite(y) else 0)

        if not x_values:
            return ChartData(chart_type="bar", error_message="No valid data for bar chart.", is_valid=False)

        return ChartData(
            chart_type="bar",
            title=f"{y_field} by {x_field}",
            x_label=x_field,
            y_label=y_field,
            x_values=x_values,
            y_values=y_values,
            is_valid=True,
        )

    def prepare_line_data(
        self,
        entries: List[DatasetEntry],
        x_field: str = "name",
        y_field: str = "mean_val",
    ) -> ChartData:
        """Prepare data for a line chart."""
        return self._prepare_xy_data(entries, x_field, y_field, "line")

    def prepare_scatter_data(
        self,
        entries: List[DatasetEntry],
        x_field: str = "min_val",
        y_field: str = "max_val",
    ) -> ChartData:
        """Prepare data for a scatter plot."""
        return self._prepare_xy_data(entries, x_field, y_field, "scatter")

    def prepare_histogram_data(
        self,
        entries: List[DatasetEntry],
        field_name: str = "mean_val",
        bins: int = 20,
    ) -> ChartData:
        """Prepare data for a histogram."""
        values = self._extract_field_values(entries, field_name)
        if not values:
            return ChartData(chart_type="histogram", error_message="No numerical data.", is_valid=False)

        try:
            hist, bin_edges = np.histogram(values, bins=min(bins, len(values)))
            x_values = [f"{bin_edges[i]:.2f}" for i in range(len(hist))]
            y_values = [float(h) for h in hist]
        except Exception as exc:
            return ChartData(chart_type="histogram", error_message=str(exc), is_valid=False)

        return ChartData(
            chart_type="histogram",
            title=f"Distribution of {field_name}",
            x_label=field_name,
            y_label="Frequency",
            x_values=x_values,
            y_values=y_values,
            is_valid=True,
        )

    def prepare_heatmap_data(
        self,
        entries: List[DatasetEntry],
        row_field: str = "name",
        col_field: str = "dtype",
        value_field: str = "mean_val",
    ) -> ChartData:
        """Prepare data for a heatmap."""
        if not entries:
            return ChartData(chart_type="heatmap", error_message="No data.", is_valid=False)

        rows = sorted(set(str(self._get_entry_field(e, row_field) or "?") for e in entries))
        cols = sorted(set(str(self._get_entry_field(e, col_field) or "?") for e in entries))

        if not rows or not cols:
            return ChartData(chart_type="heatmap", error_message="Insufficient dimensions.", is_valid=False)

        matrix = np.zeros((len(rows), len(cols)))
        row_idx = {r: i for i, r in enumerate(rows)}
        col_idx = {c: i for i, c in enumerate(cols)}

        for entry in entries:
            r = str(self._get_entry_field(entry, row_field) or "?")
            c = str(self._get_entry_field(entry, col_field) or "?")
            v = self._get_entry_field(entry, value_field)
            if v is not None and isinstance(v, (int, float)) and math.isfinite(v):
                ri = row_idx.get(r, 0)
                ci = col_idx.get(c, 0)
                matrix[ri, ci] = v

        return ChartData(
            chart_type="heatmap",
            title=f"{value_field} — {row_field} × {col_field}",
            categories=rows,
            x_values=cols,
            matrix=matrix,
            is_valid=True,
        )

    # ------------------------------------------------------------------
    # Auto visualization recommendation
    # ------------------------------------------------------------------

    def auto_recommend_visualization(
        self, entries: List[DatasetEntry]
    ) -> str:
        """
        Inspect entries and recommend an appropriate chart type.

        Returns a VisualizationType string.
        """
        if not entries:
            return "bar_chart"

        n = len(entries)
        numerical_count = sum(
            1 for e in entries
            if e.has_data and e.mean_val is not None
        )

        # If very few entries, bar chart is usually best
        if n <= 10:
            return "bar_chart"

        # If all numerical with mean/std, histogram is good
        if numerical_count == n and n > 5:
            return "histogram"

        # If we have categorical variety
        names = [e.name for e in entries]
        unique_names = len(set(names))
        if unique_names <= 8 and numerical_count > 0:
            return "pie_chart"

        # If many entries, scatter can show relationships
        if n > 10 and numerical_count >= 2:
            return "scatter_plot"

        return "bar_chart"

    # ------------------------------------------------------------------
    # Filter logic
    # ------------------------------------------------------------------

    def apply_filters(
        self,
        entries: List[DatasetEntry],
        filter_group: Any,  # FilterGroup
    ) -> List[DatasetEntry]:
        """Apply filter group to entries."""
        if filter_group is None or filter_group.is_empty:
            return entries

        return [e for e in entries if self._matches_group(e, filter_group)]

    def _matches_group(self, entry: DatasetEntry, group: Any) -> bool:
        """Check if an entry matches a filter group."""
        from pyasl.gui.models.result_ui_state import FilterLogic

        if group.logic == FilterLogic.AND:
            for rule in group.rules:
                if not self._matches_rule(entry, rule):
                    return False
            for sub in group.groups:
                if not self._matches_group(entry, sub):
                    return False
            return True
        else:  # OR
            if not group.rules and not group.groups:
                return True
            for rule in group.rules:
                if self._matches_rule(entry, rule):
                    return True
            for sub in group.groups:
                if self._matches_group(entry, sub):
                    return True
            return False

    def _matches_rule(self, entry: DatasetEntry, rule: Any) -> bool:
        """Check if an entry matches a single filter rule."""
        from pyasl.gui.models.result_ui_state import FilterOperator

        val = self._get_entry_field(entry, rule.field)

        if rule.operator == FilterOperator.IS_NULL:
            return val is None
        if rule.operator == FilterOperator.IS_NOT_NULL:
            return val is not None

        if val is None:
            return False

        rule_val = rule.value

        try:
            if rule.operator == FilterOperator.EQUALS:
                return str(val) == str(rule_val)
            elif rule.operator == FilterOperator.NOT_EQUALS:
                return str(val) != str(rule_val)
            elif rule.operator == FilterOperator.CONTAINS:
                return str(rule_val).lower() in str(val).lower()
            elif rule.operator == FilterOperator.NOT_CONTAINS:
                return str(rule_val).lower() not in str(val).lower()
            elif rule.operator == FilterOperator.GREATER_THAN:
                return float(val) > float(rule_val)
            elif rule.operator == FilterOperator.LESS_THAN:
                return float(val) < float(rule_val)
            elif rule.operator == FilterOperator.GREATER_EQUAL:
                return float(val) >= float(rule_val)
            elif rule.operator == FilterOperator.LESS_EQUAL:
                return float(val) <= float(rule_val)
            elif rule.operator == FilterOperator.BETWEEN:
                return float(rule_val) <= float(val) <= float(rule.value2)
        except (ValueError, TypeError):
            return False

        return False

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_entries(
        self,
        entries: List[DatasetEntry],
        query: str,
    ) -> List[DatasetEntry]:
        """Search entries across visible fields."""
        if not query or not query.strip():
            return entries

        q = query.lower().strip()
        results = []
        for entry in entries:
            searchable = " ".join([
                entry.name,
                entry.description,
                entry.dtype,
                str(entry.shape) if entry.shape else "",
                entry.file_path,
            ]).lower()
            if q in searchable:
                results.append(entry)
        return results

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    def sort_entries(
        self,
        entries: List[DatasetEntry],
        sort_specs: List[Any],  # List[SortSpec]
    ) -> List[DatasetEntry]:
        """Sort entries by multiple fields."""
        if not sort_specs:
            return entries

        from pyasl.gui.models.result_ui_state import SortDirection

        result = list(entries)
        for spec in reversed(sort_specs):
            reverse = spec.direction == SortDirection.DESC

            def key_fn(e, f=spec.field):
                val = self._get_entry_field(e, f)
                if val is None:
                    return (1, "")  # nulls last
                if isinstance(val, (int, float)):
                    return (0, val)
                return (0, str(val).lower())

            result.sort(key=key_fn, reverse=reverse)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_xy_data(
        self,
        entries: List[DatasetEntry],
        x_field: str,
        y_field: str,
        chart_type: str,
    ) -> ChartData:
        """Prepare generic X/Y data."""
        if not entries:
            return ChartData(chart_type=chart_type, error_message="No data.", is_valid=False)

        x_values = []
        y_values = []

        for entry in entries:
            x = self._get_entry_field(entry, x_field)
            y = self._get_entry_field(entry, y_field)
            if x is not None and y is not None:
                x_values.append(x if isinstance(x, (int, float)) else str(x))
                y_values.append(float(y) if isinstance(y, (int, float)) else 0)

        if not x_values:
            return ChartData(
                chart_type=chart_type,
                error_message=f"No valid data for {chart_type} chart.",
                is_valid=False,
            )

        return ChartData(
            chart_type=chart_type,
            title=f"{y_field} vs {x_field}",
            x_label=x_field,
            y_label=y_field,
            x_values=x_values,
            y_values=y_values,
            is_valid=True,
        )

    @staticmethod
    def _get_entry_field(entry: DatasetEntry, field_name: str) -> Any:
        """Get a field value from a DatasetEntry."""
        # Direct attributes
        if hasattr(entry, field_name):
            return getattr(entry, field_name)
        # Metadata dict
        if field_name in entry.metadata:
            return entry.metadata[field_name]
        return None

    @staticmethod
    def _extract_field_values(
        entries: List[DatasetEntry], field_name: str
    ) -> List[float]:
        """Extract numerical values for a field across entries."""
        values = []
        for entry in entries:
            val = AnalyticsService._get_entry_field(entry, field_name)
            if val is not None and isinstance(val, (int, float)) and math.isfinite(val):
                values.append(float(val))
        return values

    @staticmethod
    def get_available_fields(entries: List[DatasetEntry]) -> List[str]:
        """Return list of available field names from entries."""
        fields = [
            "name", "dtype", "ndim", "size",
            "min_val", "max_val", "mean_val", "std_val",
            "description",
        ]
        # Add any metadata keys
        meta_keys: set = set()
        for entry in entries:
            meta_keys.update(entry.metadata.keys())
        fields.extend(sorted(meta_keys))
        return fields

    @staticmethod
    def get_numerical_fields(entries: List[DatasetEntry]) -> List[str]:
        """Return fields that contain numerical data."""
        return ["min_val", "max_val", "mean_val", "std_val", "size", "ndim"]

    @staticmethod
    def get_categorical_fields(entries: List[DatasetEntry]) -> List[str]:
        """Return fields that contain categorical data."""
        return ["name", "dtype", "description"]
