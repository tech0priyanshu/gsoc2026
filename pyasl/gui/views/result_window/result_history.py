"""
gui/views/result_window/result_history.py
--------------------------------------------
Result History dialog for browsing, opening, exporting,
and deleting saved results.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
        QHeaderView, QMessageBox, QSizePolicy,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ResultHistory(QDialog):
    """
    Modal dialog listing all saved results.

    Layout::

        Result History
        ─────────────────────────────────────────
        🔍 Search…
        ─────────────────────────────────────────
        Name      Created      Records    Open  Export  Delete
        result1   2024-01-15   12,480     [O]   [E]    [D]
        ...
        ─────────────────────────────────────────
        [Close]
    """

    result_opened = pyqtSignal(str)   # result_id
    result_exported = pyqtSignal(str)  # result_id
    result_deleted = pyqtSignal(str)   # result_id

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self.setWindowTitle("Result History")
        self.setMinimumSize(700, 450)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.setStyleSheet(
            f"QDialog {{ background: {Colors.BG_PRIMARY}; }}"
        )

        # Title
        title = QLabel("Result History")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(title)

        # Search
        self._search = QLineEdit()
        self._search.setAccessibleName("Search result history")
        self._search.setPlaceholderText("🔍 Search saved results…")
        self._search.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {Colors.BG_SECONDARY}; "
            f"color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 4px; padding: 0 {Spacing.SM}px; }}"
        )
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        # Table
        self._table = QTableWidget()
        self._table.setAccessibleName("Saved results table")
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Name", "Created", "Datasets", "ASL Version", "Result ID", ""
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; gridline-color: {Colors.BORDER}; "
            f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; }}"
            f"QHeaderView::section {{ background: {Colors.BG_TERTIARY}; "
            f"color: {Colors.TEXT_SECONDARY}; border: 1px solid {Colors.BORDER}; "
            f"padding: 6px; font-weight: bold; font-size: 11px; }}"
            f"QTableWidget::item:selected {{ background: {Colors.BG_TERTIARY}; }}"
        )
        layout.addWidget(self._table, stretch=1)

        # Actions row
        actions = QHBoxLayout()
        actions.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setAccessibleName("Close history dialog")
        close_btn.setFixedHeight(DesignTokens.TOOLBAR_BTN_HEIGHT)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_TERTIARY}; color: {Colors.TEXT_PRIMARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; "
            f"padding: 0 {Spacing.LG}px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_SECONDARY}; }}"
        )
        close_btn.clicked.connect(self.close)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

    def load_history(self):
        """Populate the table from the repository."""
        self._table.setRowCount(0)

        try:
            results = self._service.list_results()
        except Exception as exc:
            logger.exception("Failed to load result history")
            return

        for result_meta in results:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name = result_meta.get("source_name", "Untitled")
            created = result_meta.get("created_at", "—")
            datasets = str(result_meta.get("dataset_count", 0))
            version = result_meta.get("asl_version", "—")
            result_id = result_meta.get("result_id", "")

            self._table.setItem(row, 0, QTableWidgetItem(name))
            self._table.setItem(row, 1, QTableWidgetItem(str(created)))
            self._table.setItem(row, 2, QTableWidgetItem(datasets))
            self._table.setItem(row, 3, QTableWidgetItem(version))
            self._table.setItem(row, 4, QTableWidgetItem(result_id))

            # Action buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            open_btn = QPushButton("Open")
            open_btn.setAccessibleName(f"Open result {name}")
            open_btn.setFixedHeight(24)
            open_btn.setStyleSheet(
                f"QPushButton {{ background: {Colors.ACCENT_PRIMARY}; color: white; "
                f"border: none; border-radius: 3px; padding: 0 8px; font-size: 10px; }}"
            )
            rid = result_id
            open_btn.clicked.connect(lambda checked, r=rid: self._on_open(r))
            actions_layout.addWidget(open_btn)

            export_btn = QPushButton("Export")
            export_btn.setAccessibleName(f"Export result {name}")
            export_btn.setFixedHeight(24)
            export_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {Colors.TEXT_SECONDARY}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 3px; "
                f"padding: 0 8px; font-size: 10px; }}"
            )
            export_btn.clicked.connect(lambda checked, r=rid: self._on_export(r))
            actions_layout.addWidget(export_btn)

            delete_btn = QPushButton("Delete")
            delete_btn.setAccessibleName(f"Delete result {name}")
            delete_btn.setFixedHeight(24)
            delete_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {Colors.ERROR}; "
                f"border: 1px solid {Colors.ERROR}; border-radius: 3px; "
                f"padding: 0 8px; font-size: 10px; }}"
            )
            delete_btn.clicked.connect(lambda checked, r=rid, n=name: self._on_delete(r, n))
            actions_layout.addWidget(delete_btn)

            self._table.setCellWidget(row, 5, actions_widget)

    def _on_search(self, text: str):
        """Filter table rows by search text."""
        text = text.lower()
        for row in range(self._table.rowCount()):
            visible = False
            for col in range(self._table.columnCount() - 1):
                item = self._table.item(row, col)
                if item and text in item.text().lower():
                    visible = True
                    break
            self._table.setRowHidden(row, not visible)

    def _on_open(self, result_id: str):
        self.result_opened.emit(result_id)
        self.close()

    def _on_export(self, result_id: str):
        self.result_exported.emit(result_id)

    def _on_delete(self, result_id: str, name: str):
        reply = QMessageBox.question(
            self, "Delete Result",
            f"Are you sure you want to delete '{name}'?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.result_deleted.emit(result_id)
            self.load_history()  # Refresh

    def showEvent(self, event):
        super().showEvent(event)
        self.load_history()
