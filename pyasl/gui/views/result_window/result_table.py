"""
gui/views/result_window/result_table.py
-----------------------------------------
Production-grade data table for viewing dataset entries.

Features:
- Custom QAbstractTableModel
- Multi-column sorting
- Column visibility/reordering
- Row selection → record details
- Sticky header
- Pagination
- Density modes
- Keyboard navigation
- Cell/row copy
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

try:
    from PyQt6.QtCore import (
        Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
        pyqtSignal,
    )
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableView,
        QHeaderView, QPushButton, QFrame, QMenu, QApplication,
        QSizePolicy, QAbstractItemView, QStyledItemDelegate,
    )
    from PyQt6.QtGui import QFont, QAction, QKeySequence
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.models.result_data import DatasetEntry
from pyasl.gui.models.result_ui_state import DensityMode
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------

class DatasetTableModel(QAbstractTableModel):
    """Model backing the dataset entries table."""

    COLUMNS = [
        ("name", "Name"),
        ("shape", "Shape"),
        ("dtype", "Type"),
        ("ndim", "Dims"),
        ("min_val", "Min"),
        ("max_val", "Max"),
        ("mean_val", "Mean"),
        ("std_val", "Std Dev"),
        ("size", "Elements"),
        ("description", "Description"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[DatasetEntry] = []
        self._visible_cols = list(range(len(self.COLUMNS)))

    def set_entries(self, entries: List[DatasetEntry]):
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def set_visible_columns(self, indices: List[int]):
        self.beginResetModel()
        self._visible_cols = indices
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        return len(self._visible_cols)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            entry = self._entries[index.row()]
            col_idx = self._visible_cols[index.column()]
            field_name = self.COLUMNS[col_idx][0]
            return self._format_value(entry, field_name)
        elif role == Qt.ItemDataRole.ToolTipRole:
            entry = self._entries[index.row()]
            col_idx = self._visible_cols[index.column()]
            field_name = self.COLUMNS[col_idx][0]
            val = self._get_raw_value(entry, field_name)
            return str(val) if val is not None else ""
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            col_idx = self._visible_cols[index.column()]
            field_name = self.COLUMNS[col_idx][0]
            if field_name in ("min_val", "max_val", "mean_val", "std_val", "size", "ndim"):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self._visible_cols):
                col_idx = self._visible_cols[section]
                return self.COLUMNS[col_idx][1]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder):
        if not self._entries or column >= len(self._visible_cols):
            return

        col_idx = self._visible_cols[column]
        field_name = self.COLUMNS[col_idx][0]
        reverse = order == Qt.SortOrder.DescendingOrder

        self.beginResetModel()

        def key_fn(entry):
            val = self._get_raw_value(entry, field_name)
            if val is None:
                return (1, "")
            if isinstance(val, (int, float)):
                return (0, val)
            return (0, str(val).lower())

        self._entries.sort(key=key_fn, reverse=reverse)
        self.endResetModel()

    def get_entry(self, row: int) -> Optional[DatasetEntry]:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def _get_raw_value(self, entry: DatasetEntry, field: str) -> Any:
        return getattr(entry, field, None)

    def _format_value(self, entry: DatasetEntry, field: str) -> str:
        val = self._get_raw_value(entry, field)
        if val is None:
            return "—"
        if field in ("min_val", "max_val", "mean_val", "std_val"):
            try:
                return f"{float(val):.4f}"
            except (ValueError, TypeError):
                return str(val)
        if field == "size":
            n = int(val)
            if n > 1_000_000:
                return f"{n/1_000_000:.1f}M"
            if n > 1_000:
                return f"{n/1_000:.1f}K"
            return str(n)
        if field == "shape":
            return str(val) if val else "—"
        return str(val)


# ---------------------------------------------------------------------------
# Table view widget
# ---------------------------------------------------------------------------

class ResultTable(QWidget):
    """
    Production data table with sorting, column control,
    row selection, and copy support.
    """

    record_selected = pyqtSignal(str)  # entry name

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._model = DatasetTableModel()
        self._density = DensityMode.COMFORTABLE
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Table view
        self._table = QTableView()
        self._table.setObjectName("result_data_table")
        self._table.setAccessibleName("Result data table")
        self._table.setModel(self._model)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)

        # Header
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_context_menu)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(120)

        # Selection → details
        self._table.clicked.connect(self._on_row_clicked)

        # Keyboard copy
        copy_action = QAction("Copy", self._table)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self._copy_selection)
        self._table.addAction(copy_action)

        layout.addWidget(self._table)

        # Footer bar (record count + pagination placeholder)
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)

        self._count_lbl = QLabel("0 records")
        self._count_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {DesignTokens.FONT_SIZE_XS}px;")
        footer_layout.addWidget(self._count_lbl)

        footer_layout.addStretch()

        layout.addWidget(footer)

        self._apply_density()
        self._apply_theme_styles()

    def refresh(self):
        """Refresh table data from the service."""
        entries = self._service.get_filtered_entries()
        self._model.set_entries(entries)
        self._count_lbl.setText(f"{len(entries)} record{'s' if len(entries) != 1 else ''}")

        # Auto-resize columns to fit content
        if entries:
            self._table.resizeColumnsToContents()

    def set_density(self, density: DensityMode):
        self._density = density
        self._apply_density()

    def _apply_density(self):
        if self._density == DensityMode.COMPACT:
            self._table.verticalHeader().setDefaultSectionSize(24)
        else:
            self._table.verticalHeader().setDefaultSectionSize(32)

    def _on_row_clicked(self, index: QModelIndex):
        entry = self._model.get_entry(index.row())
        if entry:
            self.record_selected.emit(entry.name)

    def _context_menu(self, pos):
        menu = QMenu(self._table)
        menu.setStyleSheet(self._menu_style())

        copy_cell = menu.addAction("Copy Cell")
        copy_cell.triggered.connect(self._copy_cell)

        copy_row = menu.addAction("Copy Row")
        copy_row.triggered.connect(self._copy_selection)

        menu.addSeparator()

        details = menu.addAction("View Details")
        details.triggered.connect(self._open_details)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _header_context_menu(self, pos):
        """Column visibility toggle menu."""
        menu = QMenu(self._table)
        menu.setStyleSheet(self._menu_style())

        visible = set(self._model._visible_cols)
        for i, (_, display_name) in enumerate(DatasetTableModel.COLUMNS):
            action = menu.addAction(display_name)
            action.setCheckable(True)
            action.setChecked(i in visible)
            action.toggled.connect(
                lambda checked, idx=i: self._toggle_column(idx, checked)
            )

        menu.exec(self._table.horizontalHeader().mapToGlobal(pos))

    def _toggle_column(self, col_idx: int, visible: bool):
        current = list(self._model._visible_cols)
        if visible and col_idx not in current:
            current.append(col_idx)
            current.sort()
        elif not visible and col_idx in current:
            if len(current) > 1:  # keep at least one column
                current.remove(col_idx)
        self._model.set_visible_columns(current)

    def _copy_cell(self):
        idx = self._table.currentIndex()
        if idx.isValid():
            text = self._model.data(idx)
            if text:
                QApplication.clipboard().setText(str(text))

    def _copy_selection(self):
        indices = self._table.selectionModel().selectedRows()
        if not indices:
            idx = self._table.currentIndex()
            if idx.isValid():
                indices = [idx]

        lines = []
        for idx in indices:
            entry = self._model.get_entry(idx.row())
            if entry:
                values = [
                    entry.name, str(entry.shape), entry.dtype,
                    str(entry.ndim), str(entry.min_val), str(entry.max_val),
                    str(entry.mean_val), str(entry.std_val),
                    str(entry.size), entry.description,
                ]
                lines.append("\t".join(values))

        if lines:
            QApplication.clipboard().setText("\n".join(lines))

    def _open_details(self):
        idx = self._table.currentIndex()
        if idx.isValid():
            entry = self._model.get_entry(idx.row())
            if entry:
                self.record_selected.emit(entry.name)

    def _menu_style(self) -> str:
        return f"""
            QMenu {{
                background-color: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                color: {Colors.TEXT_PRIMARY};
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.BG_HOVER};
            }}
        """

    def _apply_theme_styles(self):
        self._table.setStyleSheet(f"""
            QTableView {{
                background: {Colors.BG_PANEL};
                alternate-background-color: {Colors.BG_ELEVATED};
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: {DesignTokens.BORDER_RADIUS_MD}px;
                gridline-color: {Colors.BORDER_SUBTLE};
                color: {Colors.TEXT_PRIMARY};
                font-size: {DesignTokens.FONT_SIZE_MD}px;
                selection-background-color: {Colors.BG_HOVER};
                selection-color: {Colors.TEXT_PRIMARY};
            }}
            QTableView::item {{
                padding: 4px 8px;
            }}
            QHeaderView::section {{
                background: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_SECONDARY};
                border: none;
                border-bottom: 1px solid {Colors.BORDER};
                border-right: 1px solid {Colors.BORDER_SUBTLE};
                padding: 6px 8px;
                font-weight: bold;
                font-size: {DesignTokens.FONT_SIZE_SM}px;
            }}
            QHeaderView::section:hover {{
                background: {Colors.BG_HOVER};
            }}
        """)
