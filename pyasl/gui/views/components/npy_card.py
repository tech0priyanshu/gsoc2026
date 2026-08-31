"""
gui/views/components/npy_card.py
---------------------------------
Self-contained card widget for displaying one .npy file visualization.

Shows metadata (filename, shape, dtype, min/max, description) and the
rendered plot image. If the file failed to load, shows a warning banner.
Supports both dark and light themes via the Colors class.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve  # type: ignore
    from PyQt6.QtGui import QPixmap, QImage, QCursor  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QFrame, QSizePolicy, QPushButton, QGraphicsOpacityEffect,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import Colors


class NpyCard(QWidget):
    """
    Card widget for a single .npy visualization.

    Parameters
    ----------
    data : dict
        Visualization data with keys: path, metadata, png_bytes, error.
    parent : QWidget, optional
    """

    def __init__(self, data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self._data = data
        self._collapsed = False
        # Store references for theme refresh
        self._themed_widgets: list = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(0)

        # Outer card frame
        self._card = QFrame()
        self._card.setObjectName("npyCard")
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(4)

        metadata = self._data.get("metadata", {})
        error = self._data.get("error")

        # ── Header row: icon + filename + collapse toggle ─────
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        filename = metadata.get("filename", "unknown.npy")

        # File icon
        self._icon_lbl = QLabel("📄")
        header_layout.addWidget(self._icon_lbl)

        # Filename
        self._title_lbl = QLabel(filename)
        header_layout.addWidget(self._title_lbl)
        header_layout.addStretch()

        # Collapse / expand toggle
        self._toggle_btn = QPushButton("▼")
        self._toggle_btn.setFixedSize(24, 24)
        self._toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._toggle_btn.setToolTip("Collapse / expand this visualization")
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self._toggle_btn)

        card_layout.addLayout(header_layout)

        # ── Collapsible content ──────────────────────────────
        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 4, 0, 0)
        content_layout.setSpacing(4)

        # ── Metadata badges row ──────────────────────────────
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(6)
        badges_layout.setContentsMargins(0, 0, 0, 0)

        shape = metadata.get("shape")
        dtype = metadata.get("dtype")
        ndim = metadata.get("ndim")
        arr_min = metadata.get("min")
        arr_max = metadata.get("max")
        description = metadata.get("description", "")

        self._badge_labels: list = []
        self._ndim_badge: Optional[QLabel] = None

        if shape is not None:
            shape_str = "×".join(str(s) for s in shape)
            shape_badge = QLabel(f"⊞ {shape_str}")
            shape_badge.setToolTip(f"Array shape: {shape}")
            badges_layout.addWidget(shape_badge)
            self._badge_labels.append(shape_badge)

        if dtype is not None:
            dtype_badge = QLabel(f"⌗ {dtype}")
            dtype_badge.setToolTip(f"Data type: {dtype}")
            badges_layout.addWidget(dtype_badge)
            self._badge_labels.append(dtype_badge)

        if ndim is not None:
            ndim_badge = QLabel(f"{ndim}D")
            ndim_badge.setToolTip(f"Dimensionality: {ndim}D array")
            badges_layout.addWidget(ndim_badge)
            self._ndim_badge = ndim_badge

        badges_layout.addStretch()
        content_layout.addLayout(badges_layout)

        # ── Min/Max stats ────────────────────────────────────
        self._stats_label: Optional[QLabel] = None
        if arr_min is not None and arr_max is not None:
            self._stats_label = QLabel(
                f"↓ min: {arr_min:.6g}   ↑ max: {arr_max:.6g}"
            )
            self._stats_label.setToolTip("Minimum and maximum values in the array")
            content_layout.addWidget(self._stats_label)

        self._desc_label: Optional[QLabel] = None
        if description:
            self._desc_label = QLabel(description)
            content_layout.addWidget(self._desc_label)

        # ── Separator ────────────────────────────────────────
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        content_layout.addWidget(self._sep)

        # ── Image or Warning ─────────────────────────────────
        self._img_label: Optional[QLabel] = None
        self._warning_frame: Optional[QFrame] = None
        self._warning_icon: Optional[QLabel] = None
        self._warning_msg: Optional[QLabel] = None

        if error:
            self._add_warning(content_layout, error)
        else:
            png_bytes = self._data.get("png_bytes")
            if png_bytes:
                self._add_image(content_layout, png_bytes)
            else:
                self._add_warning(content_layout, "No image data available.")

        card_layout.addWidget(self._content_widget)
        layout.addWidget(self._card)

        # Apply initial styles
        self._apply_theme_styles()

    def _apply_theme_styles(self):
        """Apply/re-apply all inline styles using current Colors values."""
        # Card frame
        self._update_card_style(hovered=False)

        # Icon
        self._icon_lbl.setStyleSheet(
            "background: transparent; border: none; font-size: 14px;"
        )

        # Title
        self._title_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; "
            f"color: {Colors.TEXT_PRIMARY}; "
            f"background: transparent; border: none;"
        )

        # Toggle button
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ "
            f"  background: {Colors.BG_ELEVATED}; "
            f"  color: {Colors.TEXT_SECONDARY}; "
            f"  border: 1px solid {Colors.BORDER}; "
            f"  border-radius: 12px; "
            f"  font-size: 10px; "
            f"}}"
            f"QPushButton:hover {{ "
            f"  background: {Colors.BG_HOVER}; "
            f"  color: {Colors.TEXT_PRIMARY}; "
            f"}}"
        )

        # Badge labels
        badge_style = (
            f"background: {Colors.BG_ELEVATED}; "
            f"color: {Colors.TEXT_SECONDARY}; "
            f"border: 1px solid {Colors.BORDER}; "
            f"border-radius: 10px; "
            f"padding: 2px 10px; "
            f"font-size: 11px; "
            f"font-family: monospace;"
        )
        for badge in self._badge_labels:
            badge.setStyleSheet(badge_style)

        # Ndim badge (accent-colored)
        if self._ndim_badge:
            self._ndim_badge.setStyleSheet(
                f"background: {Colors.DARK_PURPLE}; "
                f"color: #ffffff; "
                f"border: none; "
                f"border-radius: 10px; "
                f"padding: 2px 10px; "
                f"font-size: 11px; "
                f"font-weight: bold;"
            )

        # Stats label
        if self._stats_label:
            self._stats_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; "
                f"font-size: 11px; font-family: monospace; "
                f"background: transparent; border: none;"
            )

        # Description label
        if self._desc_label:
            self._desc_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; "
                f"font-size: 11px; font-style: italic; "
                f"background: transparent; border: none;"
            )

        # Separator
        self._sep.setStyleSheet(
            f"background: {Colors.BORDER}; "
            f"border: none; max-height: 1px; margin: 2px 0;"
        )

        # Image label
        if self._img_label:
            self._img_label.setStyleSheet(
                "background: transparent; border: none; padding: 4px 0;"
            )

        # Warning frame
        if self._warning_frame:
            self._warning_frame.setStyleSheet(
                f"QFrame {{ "
                f"  background: {Colors.YELLOW_BG}; "
                f"  border: 1px solid {Colors.YELLOW}; "
                f"  border-radius: 6px; "
                f"}}"
            )
        if self._warning_icon:
            self._warning_icon.setStyleSheet(
                f"font-size: 16px; color: {Colors.YELLOW}; "
                f"background: transparent; border: none;"
            )
        if self._warning_msg:
            self._warning_msg.setStyleSheet(
                f"color: {Colors.YELLOW}; font-size: 12px; "
                f"background: transparent; border: none;"
            )

    def _update_card_style(self, hovered: bool = False):
        """Update card border/shadow based on hover state."""
        border = Colors.DARK_PURPLE if hovered else Colors.BORDER
        bg = Colors.BG_ELEVATED if hovered else Colors.BG_PANEL
        self._card.setStyleSheet(
            f"QFrame#npyCard {{ "
            f"  background: {bg}; "
            f"  border: 1px solid {border}; "
            f"  border-radius: 8px; "
            f"}}"
        )

    def enterEvent(self, event):
        self._update_card_style(hovered=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_card_style(hovered=False)
        super().leaveEvent(event)

    def refresh_theme(self):
        """Re-apply all styles after a theme change."""
        self._apply_theme_styles()

    def _toggle_collapse(self):
        """Toggle the visibility of the content section."""
        self._collapsed = not self._collapsed
        self._content_widget.setVisible(not self._collapsed)
        self._toggle_btn.setText("▶" if self._collapsed else "▼")

    def _add_image(self, layout: QVBoxLayout, png_bytes: bytes):
        """Add the rendered plot image to the card."""
        img = QImage()
        img.loadFromData(png_bytes, "PNG")
        pixmap = QPixmap.fromImage(img)

        self._img_label = QLabel()
        self._img_label.setPixmap(
            pixmap.scaledToWidth(
                min(pixmap.width(), 900),
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._img_label)

    def _add_warning(self, layout: QVBoxLayout, message: str):
        """Add a warning banner instead of an image."""
        self._warning_frame = QFrame()
        warn_layout = QHBoxLayout(self._warning_frame)
        warn_layout.setContentsMargins(10, 8, 10, 8)

        self._warning_icon = QLabel("⚠")
        warn_layout.addWidget(self._warning_icon)

        self._warning_msg = QLabel(f"Could not visualize: {message}")
        self._warning_msg.setWordWrap(True)
        warn_layout.addWidget(self._warning_msg, stretch=1)

        layout.addWidget(self._warning_frame)
