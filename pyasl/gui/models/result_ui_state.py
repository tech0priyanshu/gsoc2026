"""
gui/models/result_ui_state.py
------------------------------
Mutable UI state for the Result Window dashboard.

This module is **completely separate** from the canonical
``ProcessedResult``.  Nothing here should ever mutate the
underlying processed data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ViewMode(str, Enum):
    TABLE = "table"
    SUMMARY = "summary"
    VISUALIZATION = "visualization"
    COMPARE = "compare"


class VisualizationType(str, Enum):
    AUTO = "auto"
    BAR_CHART = "bar_chart"
    PIE_CHART = "pie_chart"
    DONUT_CHART = "donut_chart"
    LINE_CHART = "line_chart"
    AREA_CHART = "area_chart"
    HISTOGRAM = "histogram"
    SCATTER_PLOT = "scatter_plot"
    GROUPED_BAR = "grouped_bar"
    STACKED_BAR = "stacked_bar"
    HEATMAP = "heatmap"


class FilterOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    BETWEEN = "between"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class FilterLogic(str, Enum):
    AND = "and"
    OR = "or"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class DensityMode(str, Enum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"


# ---------------------------------------------------------------------------
# Filter model
# ---------------------------------------------------------------------------

@dataclass
class FilterRule:
    """A single filter predicate."""

    field: str = ""
    operator: FilterOperator = FilterOperator.EQUALS
    value: Any = None
    value2: Any = None   # For BETWEEN operator

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
            "value2": self.value2,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FilterRule":
        return cls(
            field=d.get("field", ""),
            operator=FilterOperator(d.get("operator", "equals")),
            value=d.get("value"),
            value2=d.get("value2"),
        )


@dataclass
class FilterGroup:
    """A group of filter rules joined by AND or OR logic."""

    logic: FilterLogic = FilterLogic.AND
    rules: List[FilterRule] = field(default_factory=list)
    groups: List["FilterGroup"] = field(default_factory=list)  # nested

    @property
    def count(self) -> int:
        """Total number of active filter rules (including nested)."""
        total = len(self.rules)
        for g in self.groups:
            total += g.count
        return total

    @property
    def is_empty(self) -> bool:
        return self.count == 0

    def clear(self) -> None:
        self.rules.clear()
        self.groups.clear()

    def add_rule(self, rule: FilterRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, index: int) -> None:
        if 0 <= index < len(self.rules):
            self.rules.pop(index)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logic": self.logic.value,
            "rules": [r.to_dict() for r in self.rules],
            "groups": [g.to_dict() for g in self.groups],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FilterGroup":
        return cls(
            logic=FilterLogic(d.get("logic", "and")),
            rules=[FilterRule.from_dict(r) for r in d.get("rules", [])],
            groups=[FilterGroup.from_dict(g) for g in d.get("groups", [])],
        )


# ---------------------------------------------------------------------------
# Sort model
# ---------------------------------------------------------------------------

@dataclass
class SortSpec:
    """A sort specification on a single field."""

    field: str = ""
    direction: SortDirection = SortDirection.ASC

    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "direction": self.direction.value}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SortSpec":
        return cls(
            field=d.get("field", ""),
            direction=SortDirection(d.get("direction", "asc")),
        )


# ---------------------------------------------------------------------------
# Visualization config
# ---------------------------------------------------------------------------

@dataclass
class VisualizationConfig:
    """Configuration for a specific chart visualization."""

    # Common
    category_field: str = ""
    measure_field: str = ""
    aggregation: str = "count"           # count, sum, mean, min, max

    # Bar / Line / Area
    x_field: str = ""
    y_field: str = ""
    group_field: str = ""
    series_field: str = ""

    # Scatter
    size_field: str = ""

    # Heatmap
    row_field: str = ""
    col_field: str = ""
    value_field: str = ""

    # Pie options
    group_small_categories: bool = True
    small_category_threshold: float = 2.0  # percent

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category_field": self.category_field,
            "measure_field": self.measure_field,
            "aggregation": self.aggregation,
            "x_field": self.x_field,
            "y_field": self.y_field,
            "group_field": self.group_field,
            "series_field": self.series_field,
            "size_field": self.size_field,
            "row_field": self.row_field,
            "col_field": self.col_field,
            "value_field": self.value_field,
            "group_small_categories": self.group_small_categories,
            "small_category_threshold": self.small_category_threshold,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VisualizationConfig":
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# ResultUIState — the complete mutable UI state
# ---------------------------------------------------------------------------

@dataclass
class ResultUIState:
    """
    Complete mutable UI state for the Result Window.

    This is saved/restored with the result but NEVER alters
    the canonical ``ProcessedResult``.
    """

    active_view: ViewMode = ViewMode.TABLE
    visualization_type: VisualizationType = VisualizationType.AUTO
    visualization_config: VisualizationConfig = field(
        default_factory=VisualizationConfig
    )
    filters: FilterGroup = field(default_factory=FilterGroup)
    search_query: str = ""
    sorting: List[SortSpec] = field(default_factory=list)
    visible_columns: List[str] = field(default_factory=list)
    selected_record: Optional[str] = None  # entry name
    density: DensityMode = DensityMode.COMFORTABLE
    details_panel_open: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_view": self.active_view.value,
            "visualization_type": self.visualization_type.value,
            "visualization_config": self.visualization_config.to_dict(),
            "filters": self.filters.to_dict(),
            "search_query": self.search_query,
            "sorting": [s.to_dict() for s in self.sorting],
            "visible_columns": self.visible_columns,
            "selected_record": self.selected_record,
            "density": self.density.value,
            "details_panel_open": self.details_panel_open,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResultUIState":
        return cls(
            active_view=ViewMode(d.get("active_view", "table")),
            visualization_type=VisualizationType(
                d.get("visualization_type", "auto")
            ),
            visualization_config=VisualizationConfig.from_dict(
                d.get("visualization_config", {})
            ),
            filters=FilterGroup.from_dict(d.get("filters", {})),
            search_query=d.get("search_query", ""),
            sorting=[
                SortSpec.from_dict(s) for s in d.get("sorting", [])
            ],
            visible_columns=d.get("visible_columns", []),
            selected_record=d.get("selected_record"),
            density=DensityMode(d.get("density", "comfortable")),
            details_panel_open=d.get("details_panel_open", False),
        )
