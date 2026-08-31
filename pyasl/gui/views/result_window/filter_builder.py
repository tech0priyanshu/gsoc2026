"""
gui/views/result_window/filter_builder.py
-------------------------------------------
Advanced filter builder UI with AND/OR groups, multiple
filter rules, validation, and clear functionality.
"""
from __future__ import annotations

import logging
from typing import List

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QComboBox, QLineEdit, QPushButton, QFrame,
        QScrollArea, QSizePolicy,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.models.result_ui_state import (
    FilterRule, FilterGroup, FilterOperator, FilterLogic,
)
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class FilterRuleRow(QFrame):
    """Single filter rule: Field + Operator + Value."""

    removed = pyqtSignal(object)

    def __init__(self, rule: FilterRule, field_names: list, parent=None):
        super().__init__(parent)
        self._rule = rule
        self._setup(field_names)

    def _setup(self, field_names: list):
        self.setStyleSheet(
            f"QFrame {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: {Spacing.XS}px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.XS, Spacing.XS, Spacing.XS, Spacing.XS)
        layout.setSpacing(Spacing.SM)

        # Field
        self._field_combo = QComboBox()
        self._field_combo.setAccessibleName("Filter field")
        self._field_combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        for name in field_names:
            self._field_combo.addItem(name, name)
        if self._rule.field:
            idx = self._field_combo.findData(self._rule.field)
            if idx >= 0:
                self._field_combo.setCurrentIndex(idx)
        self._field_combo.currentIndexChanged.connect(self._sync)
        layout.addWidget(self._field_combo)

        # Operator
        self._op_combo = QComboBox()
        self._op_combo.setAccessibleName("Filter operator")
        self._op_combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        op_labels = {
            FilterOperator.EQUALS: "Equals",
            FilterOperator.NOT_EQUALS: "Not Equals",
            FilterOperator.GREATER_THAN: "Greater Than",
            FilterOperator.LESS_THAN: "Less Than",
            FilterOperator.GREATER_EQUAL: "≥",
            FilterOperator.LESS_EQUAL: "≤",
            FilterOperator.BETWEEN: "Between",
            FilterOperator.CONTAINS: "Contains",
            FilterOperator.NOT_CONTAINS: "Not Contains",
            FilterOperator.IS_NULL: "Is Null",
            FilterOperator.IS_NOT_NULL: "Is Not Null",
        }
        for op, label in op_labels.items():
            self._op_combo.addItem(label, op.value)
        self._op_combo.currentIndexChanged.connect(self._sync)
        layout.addWidget(self._op_combo)

        # Value
        self._value_edit = QLineEdit()
        self._value_edit.setAccessibleName("Filter value")
        self._value_edit.setPlaceholderText("Value")
        self._value_edit.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._value_edit.textChanged.connect(self._sync)
        layout.addWidget(self._value_edit)

        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setAccessibleName("Remove filter rule")
        remove_btn.setFixedSize(DesignTokens.TOOLBAR_BTN_HEIGHT, DesignTokens.TOOLBAR_BTN_HEIGHT)
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.ERROR}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; font-size: 14px; }}"
            f"QPushButton:hover {{ background: {Colors.ERROR}; color: white; }}"
        )
        remove_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(remove_btn)

    def _sync(self):
        self._rule.field = self._field_combo.currentData() or ""
        self._rule.operator = FilterOperator(self._op_combo.currentData() or "equals")
        self._rule.value = self._value_edit.text()

    @property
    def rule(self) -> FilterRule:
        self._sync()
        return self._rule


class FilterBuilder(QWidget):
    """
    Filter builder drawer/panel.

    Layout::

        Filter Builder
        ────────────────────────────────
        Logic: [AND ▼]
        ────────────────────────────────
        [Field ▼] [Operator ▼] [Value] [✕]
        [Field ▼] [Operator ▼] [Value] [✕]
        ────────────────────────────────
        [+ Add Filter]  [Clear All]  [Apply]
    """

    filters_applied = pyqtSignal()
    filters_cleared = pyqtSignal()

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._rule_rows: List[FilterRuleRow] = []
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedWidth(420)
        self.setStyleSheet(
            f"background: {Colors.BG_PRIMARY}; border-left: 1px solid {Colors.BORDER};"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        outer.setSpacing(Spacing.SM)

        # Header
        header = QHBoxLayout()
        title = QLabel("Filter Builder")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setAccessibleName("Close filter builder")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: none; font-size: 16px; }}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        outer.addLayout(header)

        # Logic selector
        logic_row = QHBoxLayout()
        logic_label = QLabel("Logic:")
        logic_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;"
        )
        logic_row.addWidget(logic_label)

        self._logic_combo = QComboBox()
        self._logic_combo.setAccessibleName("Filter logic")
        self._logic_combo.addItem("AND (all match)", FilterLogic.AND.value)
        self._logic_combo.addItem("OR (any matches)", FilterLogic.OR.value)
        self._logic_combo.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        logic_row.addWidget(self._logic_combo)
        logic_row.addStretch()
        outer.addLayout(logic_row)

        # Rules scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._rules_widget = QWidget()
        self._rules_layout = QVBoxLayout(self._rules_widget)
        self._rules_layout.setContentsMargins(0, 0, 0, 0)
        self._rules_layout.setSpacing(Spacing.XS)
        self._rules_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._rules_widget)

        outer.addWidget(scroll, stretch=1)

        # Actions
        actions = QHBoxLayout()
        add_btn = QPushButton("+ Add Filter")
        add_btn.setAccessibleName("Add new filter rule")
        add_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        add_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.ACCENT_PRIMARY}; "
            f"border: 1px solid {Colors.ACCENT_PRIMARY}; border-radius: 4px; "
            f"padding: 0 {Spacing.MD}px; font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_PRIMARY}; color: white; }}"
        )
        add_btn.clicked.connect(self._add_rule)
        actions.addWidget(add_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setAccessibleName("Clear all filters")
        clear_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: 0 {Spacing.MD}px; font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_TERTIARY}; }}"
        )
        clear_btn.clicked.connect(self._clear_all)
        actions.addWidget(clear_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setAccessibleName("Apply filters")
        apply_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        apply_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: white; "
            f"border: none; border-radius: 4px; padding: 0 {Spacing.MD}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_SECONDARY}; }}"
        )
        apply_btn.clicked.connect(self._apply)
        actions.addWidget(apply_btn)

        outer.addLayout(actions)

    def _get_field_names(self) -> list:
        result = self._service.current_result
        if not result or not result.entries:
            return []
        return [e.name for e in result.entries]

    def _add_rule(self):
        rule = FilterRule()
        field_names = self._get_field_names()
        row = FilterRuleRow(rule, field_names)
        row.removed.connect(self._remove_rule)
        self._rule_rows.append(row)
        self._rules_layout.addWidget(row)

    def _remove_rule(self, row: FilterRuleRow):
        if row in self._rule_rows:
            self._rule_rows.remove(row)
            row.deleteLater()

    def _clear_all(self):
        for row in self._rule_rows:
            row.deleteLater()
        self._rule_rows.clear()
        self.filters_cleared.emit()

    def _apply(self):
        ui = self._service.current_ui_state
        rules = [row.rule for row in self._rule_rows if row.rule.field]
        logic = FilterLogic(self._logic_combo.currentData() or "and")

        ui.filters = [FilterGroup(rules=rules, logic=logic)]
        self.filters_applied.emit()

    def _apply_theme_styles(self):
        self.setStyleSheet(
            f"background: {Colors.BG_PRIMARY}; border-left: 1px solid {Colors.BORDER};"
        )
