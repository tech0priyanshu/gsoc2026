"""
gui/views/result_window/processing_details.py
-------------------------------------------------
Collapsible section showing ASL processing provenance
and metadata.  Secondary to the main analytics UI.
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QFrame, QGridLayout,
    )
    from PyQt6.QtGui import QFont
except ImportError:
    raise ImportError("PyQt6 required.")

from pyasl.gui.constants import Colors, Spacing, DesignTokens
from pyasl.gui.services.result_service import ResultService

logger = logging.getLogger(__name__)


class ProcessingDetails(QWidget):
    """
    Collapsible provenance section at the bottom of the
    Result Window.

    Shows processing configuration, ASL library version,
    timestamps, warnings, and errors.
    """

    def __init__(self, service: ResultService, parent=None):
        super().__init__(parent)
        self._service = service
        self._expanded = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toggle header
        self._toggle_btn = QPushButton("▶ Processing Details")
        self._toggle_btn.setAccessibleName("Toggle processing details")
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_TERTIARY}; "
            f"color: {Colors.TEXT_SECONDARY}; border: none; "
            f"text-align: left; padding: {Spacing.XS}px {Spacing.SM}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_SECONDARY}; }}"
        )
        self._toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self._toggle_btn)

        # Content (hidden by default)
        self._content = QFrame()
        self._content.setStyleSheet(
            f"QFrame {{ background: {Colors.BG_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 0 0 4px 4px; "
            f"padding: {Spacing.SM}px; }}"
        )
        self._content_layout = QGridLayout(self._content)
        self._content_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        self._content_layout.setSpacing(Spacing.XS)
        self._content.hide()
        layout.addWidget(self._content)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        icon = "▼" if self._expanded else "▶"
        self._toggle_btn.setText(f"{icon} Processing Details")

    def refresh(self):
        """Rebuild the processing details from current result."""
        # Clear existing
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        result = self._service.current_result
        if not result:
            self._add_row(0, "Status", "No result loaded")
            return

        row = 0
        meta = result.processing_metadata

        self._add_row(row, "Result ID", result.result_id)
        row += 1

        self._add_row(row, "Created", str(result.created_at))
        row += 1

        if result.updated_at:
            self._add_row(row, "Updated", str(result.updated_at))
            row += 1

        self._add_row(row, "ASL Library", meta.asl_library)
        row += 1

        self._add_row(row, "ASL Version", meta.asl_version)
        row += 1

        self._add_row(row, "Source", result.source_reference or "—")
        row += 1

        if meta.config_path:
            self._add_row(row, "Configuration", meta.config_path)
            row += 1

        if result.entries:
            self._add_row(row, "Datasets", str(len(result.entries)))
            row += 1

        if meta.warnings:
            self._add_row(row, "Warnings", f"{len(meta.warnings)} warning(s)")
            row += 1
            for i, w in enumerate(meta.warnings[:5]):
                self._add_row(row, f"  Warning {i+1}", str(w))
                row += 1

        if meta.errors:
            self._add_row(row, "Errors", f"{len(meta.errors)} error(s)")
            row += 1
            for i, e in enumerate(meta.errors[:5]):
                self._add_row(row, f"  Error {i+1}", str(e))
                row += 1

    def _add_row(self, row: int, label: str, value: str):
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        val = QLabel(value)
        val.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._content_layout.addWidget(lbl, row, 0)
        self._content_layout.addWidget(val, row, 1)

    def _apply_theme_styles(self):
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_TERTIARY}; "
            f"color: {Colors.TEXT_SECONDARY}; border: none; "
            f"text-align: left; padding: {Spacing.XS}px {Spacing.SM}px; "
            f"font-size: {DesignTokens.FONT_SIZE_SM}px; }}"
            f"QPushButton:hover {{ background: {Colors.BG_SECONDARY}; }}"
        )
