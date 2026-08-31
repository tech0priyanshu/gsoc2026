"""
gui/views/settings_view.py
-----------------------------
Settings tab view.

Presents log-file configuration, batch worker count, and about info.
All business logic is delegated to ``SettingsController``.
"""
from __future__ import annotations

try:
    from PyQt6.QtCore import Qt, QTimer  # type: ignore
    from PyQt6.QtGui import QFont, QPixmap  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QFormLayout, QSpinBox, QLineEdit, QPushButton,
        QFileDialog, QMessageBox, QLabel,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.controllers.settings_controller import SettingsController
from pyasl.gui.constants import APP_VERSION, Colors


class SettingsView(QWidget):
    """Settings tab."""

    def __init__(self, controller: SettingsController, parent=None):
        super().__init__(parent)
        self._ctrl = controller
        self._setup_ui()

    def _setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(20)

        # ── Logging ──────────────────────────────────────────────
        log_grp = QGroupBox("Logging")
        log_form = QFormLayout(log_grp)
        log_form.setContentsMargins(20, 28, 20, 16)
        log_form.setSpacing(12)
        self._log_path = QLineEdit(self._ctrl.log_path)
        browse_btn = QPushButton("Browse…")
        browse_btn.setProperty("flat", "true")
        browse_btn.setFixedWidth(100)
        browse_btn.setFixedHeight(36)
        browse_btn.clicked.connect(self._browse_log)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(self._log_path)
        path_row.addWidget(browse_btn)
        log_form.addRow("Log file:", path_row)
        apply_log_btn = QPushButton("Apply Log File")
        apply_log_btn.setFixedHeight(34)
        apply_log_btn.clicked.connect(self._apply_log)
        log_form.addRow("", apply_log_btn)
        lay.addWidget(log_grp)

        # ── Batch Processing ────────────────────────────────────
        batch_grp = QGroupBox("Batch Processing")
        batch_form = QFormLayout(batch_grp)
        batch_form.setContentsMargins(20, 28, 20, 16)
        batch_form.setSpacing(12)
        self._max_workers = QSpinBox()
        self._max_workers.setRange(1,16)
        self._max_workers.setValue(self._ctrl.default_workers)
        self._max_workers.valueChanged.connect(self._on_workers_changed)
        batch_form.addRow("Default max workers:", self._max_workers)
        lay.addWidget(batch_grp)

        # ── Cache Management (GUI-10) ───────────────────────────
        cache_grp = QGroupBox("Cache Management")
        cache_lay = QVBoxLayout(cache_grp)
        cache_lay.setContentsMargins(20, 28, 20, 16)
        cache_lay.setSpacing(14)

        self._cache_size_lbl = QLabel("Cache Size: Calculating…")
        cache_lay.addWidget(self._cache_size_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._clear_all_btn = QPushButton("Clear All Cache")
        self._clear_all_btn.setProperty("danger", "true")
        self._clear_all_btn.setFixedHeight(34)
        self._clear_all_btn.clicked.connect(self._on_clear_all_cache)

        self._days_spin = QSpinBox()
        self._days_spin.setRange(1, 365)
        self._days_spin.setValue(7)
        self._days_spin.setSuffix(" days")
        self._days_spin.setFixedWidth(110)

        self._clear_old_btn = QPushButton("Clear Older Than")
        self._clear_old_btn.setFixedHeight(34)
        self._clear_old_btn.clicked.connect(self._on_clear_old_cache)

        btn_row.addWidget(self._clear_all_btn)
        btn_row.addWidget(self._days_spin)
        btn_row.addWidget(self._clear_old_btn)
        btn_row.addStretch()
        cache_lay.addLayout(btn_row)

        lay.addWidget(cache_grp)

        # ── 3-Second Periodic Timer for Cache Refresh ────────────
        self._cache_timer = QTimer(self)
        self._cache_timer.setInterval(3000)
        self._cache_timer.timeout.connect(self._refresh_cache_size)
        self._cache_timer.start()

        self._refresh_cache_size()

        # ── Application Reset ──────────────────────────────────
        reset_grp = QGroupBox("Application Reset")
        reset_lay = QVBoxLayout(reset_grp)
        reset_lay.setContentsMargins(20, 28, 20, 16)
        reset_lay.setSpacing(14)

        reset_desc = QLabel(
            "Reset all application settings, pipeline graph, batch processing queue, "
            "execution history, and persistent session data back to factory defaults."
        )
        reset_desc.setWordWrap(True)
        reset_lay.addWidget(reset_desc)

        reset_btn_row = QHBoxLayout()
        self._reset_app_btn = QPushButton("Reset Application to Defaults")
        self._reset_app_btn.setProperty("danger", "true")
        self._reset_app_btn.setFixedHeight(34)
        self._reset_app_btn.clicked.connect(self._on_reset_application)

        reset_btn_row.addWidget(self._reset_app_btn)
        reset_btn_row.addStretch()
        reset_lay.addLayout(reset_btn_row)

        lay.addWidget(reset_grp)

        # ── Store widget refs for theme styling ──────────────────
        self._log_grp = log_grp
        self._batch_grp = batch_grp
        self._cache_grp = cache_grp
        self._reset_grp = reset_grp
        self._browse_btn = browse_btn
        self._apply_log_btn = apply_log_btn
        self._reset_desc = reset_desc
        self._all_groups = [log_grp, batch_grp, cache_grp, reset_grp]

        lay.addStretch()

        # Apply initial inline theme styles
        self._apply_theme_styles()

        # Wire controller error signal
        self._ctrl.error.connect(
            lambda msg: QMessageBox.critical(self, "Error", msg)
        )
        self._ctrl.log_file_changed.connect(
            lambda p: QMessageBox.information(
                self, "Log File Set", f"Logging to: {p}"
            )
        )

    def _browse_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Log File", self._log_path.text(),
            "JSON Lines (*.jsonl);;All (*)",
        )
        if path:
            self._log_path.setText(path)

    def _apply_log(self):
        self._ctrl.set_log_file(self._log_path.text())

    def _on_workers_changed(self, value: int):
        self._ctrl.default_workers = value

    def closeEvent(self, event):
        if hasattr(self, "_cache_timer") and self._cache_timer.isActive():
            self._cache_timer.stop()
        if hasattr(self, "_size_thread") and self._size_thread is not None and self._size_thread.isRunning():
            self._size_thread.quit()
            self._size_thread.wait(1000)
        super().closeEvent(event)

    def _refresh_cache_size(self):
        """Asynchronously compute cache size on a background thread to prevent UI freezing."""
        import os
        cache_dir = self._ctrl.cache_dir
        if not os.path.exists(cache_dir):
            self._cache_size_lbl.setText("Cache Size: 0.00 MB")
            return

        # Prevent stacking multiple calculation threads if one is already running
        if hasattr(self, "_size_thread") and self._size_thread is not None and self._size_thread.isRunning():
            return

        from PyQt6.QtCore import QThread, pyqtSignal
        class CacheSizeThread(QThread):
            size_calculated = pyqtSignal(float)
            def run(self):
                total_bytes = 0
                for root, dirs, files in os.walk(cache_dir):
                    for f in files:
                        try:
                            total_bytes += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass
                self.size_calculated.emit(total_bytes / (1024 * 1024))

        self._size_thread = CacheSizeThread(self)
        self._size_thread.size_calculated.connect(
            lambda mb: self._cache_size_lbl.setText(f"Cache Size: {mb:.2f} MB")
        )
        self._size_thread.start()

    def _on_clear_all_cache(self):
        reply = QMessageBox.question(
            self, "Clear Cache",
            "Are you sure you want to delete ALL cached processing results?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            import shutil, os
            cache_dir = self._ctrl.cache_dir
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir, ignore_errors=True)
                os.makedirs(cache_dir, exist_ok=True)
            self._refresh_cache_size()
            QMessageBox.information(self, "Cache Cleared", "Execution cache cleared successfully.")

    def _on_clear_old_cache(self):
        days = self._days_spin.value()
        reply = QMessageBox.question(
            self, "Clear Old Cache",
            f"Are you sure you want to clear cache entries older than {days} days?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            import os, time
            cache_dir = self._ctrl.cache_dir
            now = time.time()
            cutoff = now - (days * 86400)
            if os.path.exists(cache_dir):
                for item in os.listdir(cache_dir):
                    item_path = os.path.join(cache_dir, item)
                    if os.path.isdir(item_path) and os.path.getmtime(item_path) < cutoff:
                        import shutil
                        shutil.rmtree(item_path, ignore_errors=True)
            self._refresh_cache_size()
            QMessageBox.information(self, "Cache Cleared", f"Cleared cache entries older than {days} days.")

    def _on_reset_application(self):
        reply = QMessageBox.question(
            self,
            "Reset Application",
            "Are you sure you want to reset all application settings, pipeline graph, "
            "batch queue, execution history, and session data back to defaults?\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._ctrl.reset_application()
            self._log_path.setText(self._ctrl.log_path)
            self._max_workers.setValue(self._ctrl.default_workers)
            QMessageBox.information(
                self,
                "Reset Complete",
                "All application settings and session data have been reset to default values."
            )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme_styles(self):
        """Apply/re-apply all inline styles using current Colors values."""
        C = Colors  # shorthand

        # ── Detect light vs dark theme ───────────────────────────
        is_light = C.BG_PRIMARY != "#000000"

        # ── Palette tokens ───────────────────────────────────────
        if is_light:
            page_bg       = "#f8fafc"       # cool off-white
            card_bg       = "#f8fafc"       # soft purple tint
            card_border   = "#e0dce5"       # muted purple-gray border
            input_bg      = "#f8fafc"       # pure white inputs
            input_border  = "#c5cdd8"       # visible slate border
            input_focus   = "#830085"       # brand focus ring
            title_color   = "#830085"       # brand purple for titles
            label_color   = "#1e293b"       # dark slate for labels
            desc_color    = "#64748b"       # medium gray for helper text
            cache_lbl_clr = "#334155"       # dark slate for cache value
            btn_bg        = "#830085"       # brand primary
            btn_hover     = "#9a1a9c"       # brand hover
            btn_pressed   = "#6b006d"       # brand pressed
            btn_text      = "#ffffff"
            flat_btn_bg   = "#ffffff"       # white flat button
            flat_btn_bdr  = "#830085"       # brand border
            flat_btn_text = "#830085"
            flat_btn_hvr  = "#f3e8ff"       # light purple hover
            danger_bg     = "#fef2f2"       # soft red bg
            danger_text   = "#be123c"       # deep red text
            danger_border = "#f5c6cb"       # subtle red border
            danger_hvr_bg = "#fee2e2"       # deeper red bg on hover
            spinbox_bg    = "#ffffff"
            spinbox_bdr   = "#c5cdd8"
        else:
            page_bg       = "#000000"
            card_bg       = "#120a14"       # dark purplish tint
            card_border   = "#2e1530"       # deep purple border
            input_bg      = "#0d0d0d"       # dark input bg
            input_border  = "#3a1e3c"       # visible muted border
            input_focus   = "#830085"
            title_color   = "#c87fcb"       # lighter brand for dark bg
            label_color   = "#cbd5e1"       # light slate
            desc_color    = "#8899aa"       # medium for helper
            cache_lbl_clr = "#a0aec0"
            btn_bg        = "#830085"
            btn_hover     = "#9a1a9c"
            btn_pressed   = "#6b006d"
            btn_text      = "#ffffff"
            flat_btn_bg   = "transparent"
            flat_btn_bdr  = "#830085"
            flat_btn_text = "#c87fcb"
            flat_btn_hvr  = "#1a0a1b"
            danger_bg     = "#2a0a0e"
            danger_text   = "#FE565D"
            danger_border = "#4a1015"
            danger_hvr_bg = "#3a0e12"
            spinbox_bg    = "#0d0d0d"
            spinbox_bdr   = "#3a1e3c"

        # ── Page container ───────────────────────────────────────
        self.setStyleSheet(f"""
            SettingsView {{
                background-color: {page_bg};
            }}
        """)

        # ── Card (QGroupBox) styling ─────────────────────────────
        card_qss = f"""
            QGroupBox {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 10px;
                margin-top: 20px;
                padding: 20px 18px 16px 18px;
                font-weight: 600;
                font-size: 13px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 12px;
                left: 14px;
                color: {title_color};
                font-size: 14px;
                font-weight: 700;
            }}
        """

        # ── Form label styling ───────────────────────────────────
        label_qss = f"""
            QLabel {{
                color: {label_color};
                font-size: 13px;
                font-weight: 500;
                background: transparent;
                border: none;
            }}
        """

        # ── Input fields ─────────────────────────────────────────
        input_qss = f"""
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 7px 12px;
                color: {label_color};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 2px solid {input_focus};
                padding: 6px 11px;
            }}
        """

        spinbox_qss = f"""
            QSpinBox {{
                background-color: {spinbox_bg};
                border: 1px solid {spinbox_bdr};
                border-radius: 6px;
                padding: 6px 10px;
                color: {label_color};
                font-size: 13px;
                min-height: 20px;
            }}
            QSpinBox:focus {{
                border: 2px solid {input_focus};
                padding: 5px 9px;
            }}
        """

        # ── Primary button ───────────────────────────────────────
        primary_btn_qss = f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_text};
                border: none;
                border-radius: 7px;
                padding: 7px 20px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: {btn_pressed};
            }}
        """

        # ── Flat / Browse button ─────────────────────────────────
        flat_btn_qss = f"""
            QPushButton {{
                background-color: {flat_btn_bg};
                color: {flat_btn_text};
                border: 1px solid {flat_btn_bdr};
                border-radius: 7px;
                padding: 7px 16px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {flat_btn_hvr};
                border-color: {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: {btn_pressed};
                color: {btn_text};
            }}
        """

        # ── Danger button ────────────────────────────────────────
        danger_btn_qss = f"""
            QPushButton {{
                background-color: {danger_bg};
                color: {danger_text};
                border: 1px solid {danger_border};
                border-radius: 7px;
                padding: 7px 20px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {danger_hvr_bg};
            }}
            QPushButton:pressed {{
                background-color: {danger_bg};
            }}
        """

        # ── Apply to each group ──────────────────────────────────
        for grp in self._all_groups:
            grp.setStyleSheet(card_qss + label_qss + input_qss + spinbox_qss + primary_btn_qss)

        # Override specific buttons that need different treatment
        self._browse_btn.setStyleSheet(flat_btn_qss)
        self._clear_all_btn.setStyleSheet(danger_btn_qss)
        self._reset_app_btn.setStyleSheet(danger_btn_qss)
        self._clear_old_btn.setStyleSheet(primary_btn_qss)
        self._apply_log_btn.setStyleSheet(primary_btn_qss)

        # ── Cache size label — emphasis styling ──────────────────
        self._cache_size_lbl.setStyleSheet(f"""
            QLabel {{
                color: {cache_lbl_clr};
                font-weight: 700;
                font-size: 14px;
                background: transparent;
                border: none;
                padding: 2px 0px;
            }}
        """)

        # ── Reset description — helper text ──────────────────────
        self._reset_desc.setStyleSheet(f"""
            QLabel {{
                color: {desc_color};
                font-size: 12px;
                font-weight: 400;
                line-height: 1.5;
                background: transparent;
                border: none;
                padding: 0px;
            }}
        """)

    def restore_from_settings(self, settings_data: dict) -> None:
        """Update UI widgets to reflect restored session settings."""
        log_path = settings_data.get("log_path", "")
        if log_path:
            self._log_path.setText(log_path)
        workers = settings_data.get("default_workers")
        if workers is not None:
            self._max_workers.setValue(int(workers))
