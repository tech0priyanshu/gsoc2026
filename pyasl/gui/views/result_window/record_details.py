"""
gui/views/result_window/record_details.py
--------------------------------------------
Side panel showing detailed information about a selected
DatasetEntry record.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QScrollArea, QFrame, QPushButton, QGridLayout,
        QSizePolicy,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class RecordDetails(QWidget):
    """
    Right-side details panel showing field-value pairs for a
    selected DatasetEntry.

    Desktop: side panel in splitter.
    Compact: acts as an overlay/drawer.
    """

    close_requested = pyqtSignal()

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self.setMinimumWidth(260)
        self.setMaximumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        outer.setSpacing(Spacing.SM)

        # Header
        header = QHBoxLayout()
        title = QLabel("Record Details")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; background: transparent;")
        title.setAccessibleName("Record Details panel")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setAccessibleName("Close details panel")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; "
            f"border: none; font-size: 16px; }}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        outer.addLayout(header)

        # Scroll area for details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self._detail_layout = QVBoxLayout(content)
        self._detail_layout.setContentsMargins(0, 0, 0, 0)
        self._detail_layout.setSpacing(Spacing.XS)
        self._detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content)

        outer.addWidget(scroll, stretch=1)

        # Empty state
        self._empty_label = QLabel("Select a record to view details.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 12px; padding: 20px;"
        )
        self._detail_layout.addWidget(self._empty_label)

    def show_entry(self, entry_name: str):
        """Display details for the named DatasetEntry."""
        self._clear_details()

        result = self._service.current_result
        if not result or not result.entries:
            self._empty_label.show()
            return

        entry = None
        for e in result.entries:
            if e.name == entry_name:
                entry = e
                break

        if not entry:
            self._empty_label.setText(f"Entry '{entry_name}' not found.")
            self._empty_label.show()
            return

        self._empty_label.hide()

        # Entry name
        name_label = QLabel(entry.name)
        name_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._detail_layout.addWidget(name_label)

        if entry.description:
            desc = QLabel(entry.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
            self._detail_layout.addWidget(desc)

        # Properties grid
        properties = [
            ("File Path", entry.file_path),
            ("Shape", str(entry.shape) if entry.shape else "—"),
            ("Dtype", entry.dtype),
            ("Dimensions", str(entry.ndim)),
            ("Total Elements", f"{entry.size:,}"),
        ]

        if entry.min_val is not None:
            properties.append(("Minimum", f"{entry.min_val:.6g}"))
        if entry.max_val is not None:
            properties.append(("Maximum", f"{entry.max_val:.6g}"))
        if entry.mean_val is not None:
            properties.append(("Mean", f"{entry.mean_val:.6g}"))
        if entry.std_val is not None:
            properties.append(("Std Dev", f"{entry.std_val:.6g}"))

        for label_text, value in properties:
            self._add_detail_row(label_text, value)

        # Metadata
        if entry.metadata:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"background: {Colors.BORDER};")
            self._detail_layout.addWidget(sep)

            meta_title = QLabel("Metadata")
            meta_title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
            meta_title.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            self._detail_layout.addWidget(meta_title)

            for key, val in entry.metadata.items():
                self._add_detail_row(key, str(val))

        self._detail_layout.addStretch()

    def _add_detail_row(self, label: str, value: str):
        """Add a label-value pair to the details."""
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {Colors.BG_SECONDARY}; border-radius: 4px; "
            f"padding: {Spacing.XS}px; border: none; }}"
        )
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(Spacing.XS, 2, Spacing.XS, 2)
        row_layout.setSpacing(1)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 10px; "
            f"background: transparent; border: none;"
        )
        row_layout.addWidget(lbl)

        val = QLabel(value)
        val.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; "
            f"background: transparent; border: none;"
        )
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        val.setWordWrap(True)
        row_layout.addWidget(val)

        self._detail_layout.addWidget(row)

    def _clear_details(self):
        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._empty_label:
                widget.deleteLater()

    def _apply_theme_styles(self):
        self.setStyleSheet(
            f"background: {Colors.BG_PRIMARY}; "
            f"border-left: 1px solid {Colors.BORDER};"
        )
