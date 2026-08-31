"""
gui/views/main_window.py
--------------------------
PyASL Main Application Window.

Thin shell that:
1. Creates SessionManager & CacheManager for persistence
2. Creates controllers (pipeline, batch, settings) with manager injection
3. Creates tab views (injecting their controllers)
4. Wires cross-cutting signals (e.g. pipeline → monitor)
5. Restores previous session on startup (if valid)
6. Auto-saves session on close
7. Sets up menu bar and status bar
"""
from __future__ import annotations

import logging

try:
    from PyQt6.QtCore import Qt,QUrl  # type: ignore
    from PyQt6.QtGui import QFont, QIcon, QPixmap,QDesktopServices, QAction  # type: ignore
    from PyQt6.QtWidgets import (  # type: ignore
        QMainWindow, QTabWidget, QStatusBar,
        QLabel, QMessageBox, QApplication,
        QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
        QFormLayout, QPushButton, QFileDialog, QMenu,
    )
except ImportError:
    raise ImportError("PyQt6 required. Install: pip install PyQt6")

from pyasl.gui.constants import Colors, APP_VERSION
from pyasl.gui.models.session_manager import SessionManager
from pyasl.gui.models.cache_manager import CacheManager
from pyasl.gui.models.execution_session import ExecutionSession, ExecutionSessionLogHandler
from pyasl.gui.controllers.pipeline_controller import PipelineController
from pyasl.gui.controllers.batch_controller import BatchController
from pyasl.gui.controllers.settings_controller import SettingsController
from pyasl.gui.controllers.results_controller import ResultsController
from pyasl.gui.views.pipeline_builder_view import PipelineBuilderView
from pyasl.gui.views.batch_panel_view import BatchPanelView
from pyasl.gui.views.monitor_panel_view import MonitorPanelView
from pyasl.gui.views.settings_view import SettingsView
from pyasl.gui.views.results_panel_view import ResultsPanelView

logger = logging.getLogger(__name__)


# ======================================================================
# Workspace Feature — Helper Classes
# ======================================================================


class WorkspaceManager:
    """
    Thin, Qt-free helper that manages workspace filesystem operations.

    Responsibilities:
    - Create new workspace directories with the standard sub-folder scaffold
    - Validate and open existing workspace directories
    - Provide workspace metadata (name, path, disk usage)
    - Persist / recall a "recent workspaces" list

    This class deliberately has **no Qt dependency** so it can be
    unit-tested without a running QApplication.
    """

    # Sub-directories every workspace is expected to contain
    _SCAFFOLD_DIRS = ("uploads", "cache", "logs")

    # Max entries kept in the recent-workspaces list
    MAX_RECENT = 8

    def __init__(self, current_root: str) -> None:
        from pathlib import Path
        self._current = Path(current_root).resolve()
        # Global config dir for persisting recent-workspaces
        self._config_dir = Path.home() / ".pyasl_config"
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._recent_path = self._config_dir / "recent_workspaces.json"

    # ── Properties ─────────────────────────────────────────────────

    @property
    def current_root(self):
        """Return the current workspace root as a ``pathlib.Path``."""
        from pathlib import Path
        return Path(self._current)

    @property
    def current_name(self) -> str:
        """Human-readable workspace name (basename of root)."""
        return self._current.name

    # ── Create new workspace ──────────────────────────────────────

    def create_new(self, path: str) -> bool:
        """
        Scaffold a new workspace at *path*.

        Creates the root directory (if needed) and the standard
        sub-directories (uploads/, cache/, logs/).

        Returns ``True`` on success, ``False`` on failure.
        """
        from pathlib import Path
        import os
        target = Path(path).resolve()
        try:
            target.mkdir(parents=True, exist_ok=True)
            for sub in self._SCAFFOLD_DIRS:
                (target / sub).mkdir(exist_ok=True)
            self._current = target
            self._push_recent(str(target))
            return True
        except OSError:
            logger.exception("Failed to create workspace at %s", path)
            return False

    # ── Open existing workspace ───────────────────────────────────

    def open(self, path: str) -> bool:
        """
        Validate and accept *path* as the active workspace.

        The directory must exist.  Missing scaffold sub-dirs are
        created automatically.

        Returns ``True`` on success, ``False`` if *path* is not a directory.
        """
        from pathlib import Path
        target = Path(path).resolve()
        if not target.is_dir():
            return False
        # Ensure scaffold sub-dirs exist
        for sub in self._SCAFFOLD_DIRS:
            (target / sub).mkdir(exist_ok=True)
        self._current = target
        self._push_recent(str(target))
        return True

    # ── Workspace info ────────────────────────────────────────────

    def info(self) -> dict:
        """
        Return metadata about the current workspace.

        Keys: ``name``, ``path``, ``size_bytes``, ``session_exists``.
        """
        import os
        total_bytes = 0
        root_str = str(self._current)
        for dirpath, _dirnames, filenames in os.walk(root_str):
            for f in filenames:
                try:
                    total_bytes += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        return {
            "name": self._current.name,
            "path": root_str,
            "size_bytes": total_bytes,
            "session_exists": (self._current / "session.json").is_file(),
        }

    # ── Recent workspaces ─────────────────────────────────────────

    def get_recent(self) -> list:
        """Return the list of recently used workspace paths (newest first)."""
        import json
        if not self._recent_path.is_file():
            return []
        try:
            with open(self._recent_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [str(p) for p in data]
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _push_recent(self, path: str) -> None:
        """Push *path* to the top of the recent-workspaces list and persist."""
        import json
        recent = self.get_recent()
        # Remove duplicates (case-insensitive on Windows)
        from pathlib import Path
        norm = str(Path(path).resolve())
        recent = [r for r in recent if str(Path(r).resolve()) != norm]
        recent.insert(0, norm)
        recent = recent[: self.MAX_RECENT]
        try:
            with open(self._recent_path, "w", encoding="utf-8") as f:
                json.dump(recent, f, indent=2)
        except OSError:
            logger.exception("Could not persist recent workspaces")

    def clear_recent(self) -> None:
        """Clear the recent-workspaces list."""
        import json
        try:
            with open(self._recent_path, "w", encoding="utf-8") as f:
                json.dump([], f)
        except OSError:
            pass


class WorkspaceInfoDialog(QDialog):
    """
    Modal dialog showing metadata about the active workspace.

    Displayed by **Workspace → Workspace Info** in the menu bar.
    Styled to match the existing dark/light theme system.
    """

    def __init__(self, ws_info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workspace Info")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._ws_info = ws_info
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel(" Workspace Information")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(title)

        # Info group
        info_grp = QGroupBox("Details")
        form = QFormLayout(info_grp)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)

        name_lbl = QLabel(self._ws_info.get("name", "—"))
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: bold;")
        form.addRow("Name:", name_lbl)

        path_lbl = QLabel(self._ws_info.get("path", "—"))
        path_lbl.setWordWrap(True)
        path_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        form.addRow("Path:", path_lbl)

        size_bytes = self._ws_info.get("size_bytes", 0)
        size_mb = size_bytes / (1024 * 1024)
        size_text = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_bytes / 1024:.1f} KB"
        size_lbl = QLabel(size_text)
        size_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        form.addRow("Disk usage:", size_lbl)

        session_lbl = QLabel(
            "✅  Yes" if self._ws_info.get("session_exists") else "❌  No"
        )
        session_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        form.addRow("Session file:", session_lbl)

        layout.addWidget(info_grp)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Store labels for theme-refresh access
        self._title_lbl = title
        self._name_lbl = name_lbl
        self._path_lbl = path_lbl
        self._size_lbl = size_lbl
        self._session_lbl = session_lbl



class MainWindow(QMainWindow):
    """PyASL main application window."""

    def __init__(self):
        super().__init__()
        import os
        import sys
        from pyasl.gui.utils.resource_helper import get_logo_icon

        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        # Set window icon via resource helper
        icon = get_logo_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
            app_inst = QApplication.instance()
            if app_inst:
                app_inst.setWindowIcon(icon)

        # ── Persistence managers & shared execution session ───────
        self._session = SessionManager()
        self._cache = CacheManager(self._session.cache_dir)
        self._execution_session = ExecutionSession(self)

        # Attach log handler to Python root logger so all terminal/application logs flow to Live Logs
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        log_handler = ExecutionSessionLogHandler(self._execution_session)
        root_logger.addHandler(log_handler)

        # Set window title with active workspace name
        ws_name = os.path.basename(self._session.workspace_root)
        self.setWindowTitle(f"PyASL - {ws_name}")

        # ── Controllers ─────────────────────────────────────────
        self._pipeline_ctrl = PipelineController(
            self, session=self._session
        )
        self._batch_ctrl = BatchController(
            self, session=self._session, cache=self._cache,
            execution_session=self._execution_session,
        )
        self._settings_ctrl = SettingsController(
            self, session=self._session
        )
        self._results_ctrl = ResultsController(self)

        # ── Build UI ────────────────────────────────────────────
        self._setup_tabs()
        self._monitor.set_execution_session(self._execution_session)
        self._monitor.set_batch_controller(self._batch_ctrl)
        self._setup_menu()
        self._setup_statusbar()
        self._wire_cross_signals()
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Setup context-aware keyboard shortcuts (GUI-4)."""
        from pyasl.gui.utils.shortcut_manager import ShortcutManager
        self._shortcut_mgr = ShortcutManager(self)
        self._shortcut_mgr.register_shortcut("Ctrl+S", lambda: self._pipeline_builder._on_save_yaml())
        self._shortcut_mgr.register_shortcut("F5", lambda: self._pipeline_ctrl.run())
        self._shortcut_mgr.register_shortcut("Ctrl+Q", self.close)
        self._shortcut_mgr.register_shortcut("Esc", lambda: self._batch_ctrl.abort())

        # ── Restore previous session ────────────────────────────
        self._restore_session()

    # ------------------------------------------------------------------
    # Session restoration
    # ------------------------------------------------------------------

    def _restore_session(self) -> None:
        """
        Attempt to restore a previous session on startup.

        Flow:
        1. Load session.json and validate file references.
        2. If valid → restore batch jobs, pipeline, settings silently.
        3. If some files are missing → inform the user, restore the rest.
        4. If no session or corrupted → start fresh (normal behavior).
        """
        success, missing_jobs = self._session.load()

        if not success:
            logger.info("No previous session to restore.")
            return

        # Restore settings first (theme may affect UI rendering)
        settings = self._session.get_settings()
        if settings:
            self._settings_ctrl.restore_settings(settings)
            self._settings.restore_from_settings(settings)
            # Apply theme
            theme = settings.get("theme", "dark")
            if theme and theme != "dark":
                self.set_theme(theme)

        # Restore pipeline
        pipeline_data = self._session.get_pipeline()
        if pipeline_data and pipeline_data.get("nodes"):
            self._pipeline_ctrl.restore_pipeline(pipeline_data)
            self._builder.canvas.update()
            logger.info(
                "Restored pipeline with %d nodes.",
                len(pipeline_data.get("nodes", [])),
            )

        # Restore batch jobs
        batch_jobs = self._session.get_batch_jobs()
        if batch_jobs:
            self._batch_ctrl.restore_jobs(batch_jobs)
            logger.info("Restored %d batch jobs.", len(batch_jobs))

            # Restore results for previously completed jobs
            self._restore_batch_results(batch_jobs)

        # Restore shared execution session and monitor UI
        exec_history = self._session.get_execution_history()
        if exec_history:
            self._execution_session.from_dict(exec_history)
            self._monitor.restore_from_session()
            logger.info("Restored execution history to Monitor.")

        # Notify about missing files
        if missing_jobs:
            missing_info = []
            for mj in missing_jobs:
                data_dir = mj.get("data_dir", "")
                config_path = mj.get("config_path", "")
                label = mj.get("label", mj.get("job_id", "unknown"))
                parts = [f"• {label}:"]
                import os
                if data_dir and not os.path.isdir(data_dir):
                    parts.append(f"  Data dir missing: {data_dir}")
                if config_path and not os.path.isfile(config_path):
                    parts.append(f"  Config missing: {config_path}")
                missing_info.append("\n".join(parts))

            QMessageBox.warning(
                self,
                "Session Restore — Missing Files",
                f"{len(missing_jobs)} job(s) from the previous session "
                f"reference files that no longer exist and were removed:\n\n"
                + "\n\n".join(missing_info),
            )

        # Update status bar
        n_pipeline = len(self._pipeline_ctrl.graph.nodes)
        n_batch = self._batch_ctrl.state.count
        restored_parts = []
        if n_pipeline:
            restored_parts.append(
                f"{n_pipeline} pipeline node{'s' if n_pipeline != 1 else ''}"
            )
        if n_batch:
            restored_parts.append(
                f"{n_batch} batch job{'s' if n_batch != 1 else ''}"
            )
        if restored_parts:
            self._status_lbl.setText(
                f"Session restored: {', '.join(restored_parts)}"
            )

    # ------------------------------------------------------------------
    # Restore batch results for completed jobs
    # ------------------------------------------------------------------

    def _restore_batch_results(self, batch_jobs: list) -> None:
        """
        Create Results entries for batch jobs that were already COMPLETED
        in a previous session, so their .npy outputs get visualized.
        """
        import os
        completed = [
            j for j in batch_jobs if j.get("status") == "COMPLETED"
        ]
        if not completed:
            return

        # Build a results_list matching the format expected by add_batch_result
        results_list = []
        for j in completed:
            results_list.append({
                "job_id": j.get("job_id", "unknown"),
                "status": "COMPLETED",
                "duration": j.get("duration"),
                "data_dir": j.get("data_dir", ""),
                "config_path": j.get("config_path", ""),
                "error": None,
            })

        if results_list:
            self._results_ctrl.add_batch_result(results_list)
            logger.info(
                "Restored results for %d completed batch jobs.",
                len(results_list),
            )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _setup_tabs(self):
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._builder = PipelineBuilderView(self._pipeline_ctrl)
        self._batch = BatchPanelView(self._batch_ctrl)
        self._monitor = MonitorPanelView()
        self._settings = SettingsView(self._settings_ctrl)
        self._results = ResultsPanelView(self._results_ctrl)

        self._tabs.addTab(self._builder,  "  Pipeline Builder")
        self._tabs.addTab(self._batch,    "  Batch Mode")
        self._tabs.addTab(self._monitor,  "  Monitor")
        self._tabs.addTab(self._results,  "  Results")
        self._tabs.addTab(self._settings, "  Settings")

        self.setCentralWidget(self._tabs)

    def _setup_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("File")
        file_menu.addAction(
            "   Load Pipeline YAML  ",
            lambda: self._builder._on_load_yaml(),
        )
        file_menu.addAction(
            "   Save Pipeline YAML  ",
            lambda: self._builder._on_save_yaml(),
        )

        # ── Workspace menu (additive — Workspace Feature) ──────
        self._setup_workspace_menu(mb)

        view_menu = mb.addMenu("View")
        theme_menu = view_menu.addMenu("Theme      ")  #view/theme
        
        system_action = theme_menu.addAction("System Default")
        system_action.triggered.connect(lambda: self._set_theme_with_save("system"))
        
        dark_action = theme_menu.addAction("Dark Mode")
        dark_action.triggered.connect(lambda: self._set_theme_with_save("dark"))
        
        light_action = theme_menu.addAction("Light Mode")
        light_action.triggered.connect(lambda: self._set_theme_with_save("light"))

        help_menu = mb.addMenu("Help")
        help_menu.addAction("About PyASL", self._show_about)  # help/about
        
        help_menu.addAction("Documentation", self._documentation_about)  # help/Doc

    def _setup_statusbar(self):
        sb = QStatusBar()
        self._status_lbl = QLabel("PyASL Pipeline GUI ready")
        self._status_lbl.setStyleSheet(
            f"color: {Colors.BRIGHT_CORAL}; font-size: 11px; "
            "padding: 2px 6px;"
        )
        self._elapsed_lbl = QLabel("")
        self._elapsed_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-family: monospace; padding: 2px 6px;"
        )
        sb.addWidget(self._status_lbl)
        sb.addPermanentWidget(self._elapsed_lbl)
        self.setStatusBar(sb)

        import time
        from PyQt6.QtCore import QTimer
        self._start_monotonic: float = 0.0
        self._exec_timer = QTimer(self)
        self._exec_timer.setInterval(500)
        self._exec_timer.timeout.connect(self._update_elapsed_time)

    def _start_exec_timer(self):
        import time
        self._start_monotonic = time.monotonic()
        self._elapsed_lbl.setText("Elapsed: 00:00:00")
        self._exec_timer.start()

    def _stop_exec_timer(self):
        self._exec_timer.stop()

    def _update_elapsed_time(self):
        import time
        if self._start_monotonic > 0:
            elapsed_sec = int(time.monotonic() - self._start_monotonic)
            hrs = elapsed_sec // 3600
            mins = (elapsed_sec % 3600) // 60
            secs = elapsed_sec % 60
            self._elapsed_lbl.setText(f"Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}")

    def _wire_cross_signals(self):
        """Connect pipeline controller signals → monitor panel."""
        self._pipeline_ctrl.node_status_changed.connect(
            self._monitor.on_node_status_changed,
        )
        self._pipeline_ctrl.graph_changed.connect(self._update_status)
        
        # Connect timer and loading indicators
        self._pipeline_ctrl.run_started.connect(self._start_exec_timer)
        self._batch_ctrl.batch_started.connect(self._start_exec_timer)
        self._pipeline_ctrl.run_completed.connect(lambda _: self._stop_exec_timer())
        self._batch_ctrl.batch_completed.connect(lambda _: self._stop_exec_timer())
        self._pipeline_ctrl.error.connect(lambda _: self._stop_exec_timer())
        self._batch_ctrl.error.connect(lambda _: self._stop_exec_timer())

        # Connect Pipeline results
        self._pipeline_ctrl.run_completed.connect(
            lambda msg: self._results_ctrl.add_pipeline_result(msg, {})
        )
        self._pipeline_ctrl.error.connect(self._results_ctrl.add_pipeline_error)

        # Connect Batch results
        self._batch_ctrl.batch_completed.connect(self._results_ctrl.add_batch_result)
        self._batch_ctrl.error.connect(self._results_ctrl.add_batch_error)

        # Switch to results tab on new result
        self._results_ctrl.result_added.connect(
            lambda _: self._tabs.setCurrentWidget(self._results)
        )

        # Reset application signal
        self._settings_ctrl.reset_requested.connect(self._on_application_reset)

    # ------------------------------------------------------------------
    # Reset Application
    # ------------------------------------------------------------------

    def _on_application_reset(self) -> None:
        """Handle full application reset requested from SettingsView."""
        self._pipeline_ctrl.clear()
        if hasattr(self, "_builder") and hasattr(self._builder, "canvas"):
            self._builder.canvas.update()

        self._batch_ctrl.clear()
        self._execution_session.from_dict({})
        if hasattr(self, "_monitor") and hasattr(self._monitor, "_clear"):
            self._monitor._clear()

        self._results_ctrl.clear_all()
        self.set_theme("dark")
        logger.info("Application state reset to defaults.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_status(self):
        n = len(self._pipeline_ctrl.graph.nodes)
        self._status_lbl.setText(
            f"Pipeline Builder: {n} node{'s' if n != 1 else ''} on canvas"
        )

    def _show_about(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("About PyASL")
        msg.setText("<b>PyASL Pipeline GUI</b>")
        msg.setInformativeText(
            "A graphical interface for building, executing, and monitoring\n"
            "ASL MRI processing pipelines.\n\n"
            "Built with PyQt6 · DAG pipeline engine · Batch processing\n"
            f"OSIPI TF 2.2 · GSoC 2026 · v{APP_VERSION}"
        )
        from pyasl.gui.utils.resource_helper import get_logo_pixmap
        pixmap = get_logo_pixmap(64, 64)
        if not pixmap.isNull():
            msg.setIconPixmap(pixmap)
        msg.exec()    
        
    def _documentation_about(self):
        QDesktopServices.openUrl(QUrl("https://pyasl-doc.readthedocs.io/index.html"))
        
           
        

    def _set_theme_with_save(self, theme: str):
        """Set theme and persist the choice to session."""
        self.set_theme(theme)
        self._settings_ctrl.theme = theme

    def set_theme(self, theme: str):
        from PyQt6.QtWidgets import QApplication, QWidget
        import os
        
        actual_theme = theme
        if theme == "system":
            import sys
            if sys.platform == "win32":
                try:
                    import winreg
                    registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                    key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                    value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                    actual_theme = "dark" if value == 0 else "light"
                except Exception:
                    actual_theme = "dark"
            else:
                actual_theme = "dark"

        # Update dynamic Colors class constants
        from pyasl.gui.constants import Colors
        Colors.set_theme(actual_theme)

        # Load stylesheet
        styles_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "styles")
        qss_name = "dark_theme.qss" if actual_theme == "dark" else "light_theme.qss"
        qss_path = os.path.join(styles_dir, qss_name)
        
        stylesheet = ""
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                stylesheet = f.read()
                
        QApplication.instance().setStyleSheet(stylesheet)
        
        # Refresh colors in views/widgets
        from pyasl.gui.views import node_canvas
        node_canvas.update_colors()
        
        # Update canvas overlay styles
        if hasattr(self, "_builder") and hasattr(self._builder, "canvas"):
            self._builder.canvas.update_overlay_style()

        # Sync results controller theme for plot rendering
        if hasattr(self, "_results_ctrl"):
            self._results_ctrl.theme = actual_theme

        # ── Re-apply inline styles on all tab views ──────────
        # This is the central dispatch that makes theme switching
        # propagate to all widgets using inline setStyleSheet().
        for view in (self._builder, self._batch, self._monitor,
                     self._results, self._settings):
            if hasattr(view, "_apply_theme_styles"):
                view._apply_theme_styles()

        # Re-apply status label styling dynamically
        if hasattr(self, "_status_lbl"):
            self._status_lbl.setStyleSheet(
                f"color: {Colors.BRIGHT_CORAL}; font-size: 11px; "
                "padding: 2px 6px;"
            )
            
        self.update()
        for widget in self.findChildren(QWidget):
            widget.update()

    # ------------------------------------------------------------------
    # Close behaviour — auto-save session
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Auto-save session when the window is closed."""
        try:
            self._session.save()
            logger.info("Session saved on close.")
        except Exception:
            logger.exception("Failed to save session on close.")
        super().closeEvent(event)

    def keyPressEvent(self, event):
        """Ignore Escape key so it doesn't close the window."""
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    # ==================================================================
    # Workspace Feature — Menu, Actions, and Switching
    # ==================================================================

    def _setup_workspace_menu(self, menubar):
        """
        Build the top-level **Workspace** menu and its sub-items.

        Inserted between File and View.  Contains:
          • New Workspace…
          • Open Workspace…
          • ─────────────
          • Recent Workspaces  →  (submenu with last N paths)
          • ─────────────
          • Workspace Info
        """
        self._ws_mgr = WorkspaceManager(self._session.workspace_root)
        ws_menu = menubar.addMenu("Workspace")

        ws_menu.addAction("New Workspace…", self._workspace_new)
        ws_menu.addAction("Open Workspace…", self._workspace_open)
        ws_menu.addSeparator()

        # ── Recent Workspaces submenu ─────────────────────────────
        self._recent_menu = ws_menu.addMenu("Recent Workspaces        ")
        self._refresh_recent_menu()

        ws_menu.addSeparator()
        ws_menu.addAction("Workspace Info   ", self._workspace_info)

    # ------------------------------------------------------------------
    # Recent Workspaces submenu helpers
    # ------------------------------------------------------------------

    def _refresh_recent_menu(self) -> None:
        """
        Rebuild the Recent Workspaces submenu from persisted data.

        Each entry opens that workspace when clicked.  A "Clear Recent"
        action is appended at the bottom.
        """
        self._recent_menu.clear()
        recent = self._ws_mgr.get_recent()
        if not recent:
            no_action = self._recent_menu.addAction("(no recent workspaces)")
            no_action.setEnabled(False)
            return

        for path in recent:
            import os
            display = os.path.basename(path) or path
            action = self._recent_menu.addAction(f"  {display}")
            action.setToolTip(path)
            # Capture *path* by default-arg to avoid late-binding issues
            action.triggered.connect(
                lambda checked=False, p=path: self._switch_workspace(p)
            )

        self._recent_menu.addSeparator()
        clear_action = self._recent_menu.addAction("  Clear Recent")
        clear_action.triggered.connect(self._clear_recent_workspaces)

    def _clear_recent_workspaces(self) -> None:
        """Clear the recent-workspaces list and rebuild the submenu."""
        self._ws_mgr.clear_recent()
        self._refresh_recent_menu()

    # ------------------------------------------------------------------
    # Workspace actions
    # ------------------------------------------------------------------

    def _workspace_new(self) -> None:
        """
        Prompt the user to choose a directory and create a new workspace.

        Scaffolds the standard sub-folders and switches to the new
        workspace.
        """
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose directory for new workspace",
        )
        if not chosen:
            return
        ok = self._ws_mgr.create_new(chosen)
        if not ok:
            QMessageBox.critical(
                self, "Workspace Error",
                f"Could not create workspace at:\n{chosen}",
            )
            return
        self._switch_workspace(chosen)
        self._status_lbl.setText(f"New workspace created → {chosen}")

    def _workspace_open(self) -> None:
        """
        Prompt the user to choose an existing workspace directory.

        Validates the directory and switches to it.
        """
        chosen = QFileDialog.getExistingDirectory(
            self, "Open existing workspace",
        )
        if not chosen:
            return
        ok = self._ws_mgr.open(chosen)
        if not ok:
            QMessageBox.critical(
                self, "Workspace Error",
                f"The selected path is not a valid directory:\n{chosen}",
            )
            return
        self._switch_workspace(chosen)
        self._status_lbl.setText(f"Workspace opened → {chosen}")

    def _workspace_info(self) -> None:
        """Show the Workspace Info dialog for the active workspace."""
        info = self._ws_mgr.info()
        dlg = WorkspaceInfoDialog(info, parent=self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Internal: switch workspace
    # ------------------------------------------------------------------

    def _switch_workspace(self, path: str) -> None:
        """
        Save the current session, re-initialise managers at *path*,
        and update the window title.

        The existing canvas / batch state stays visible (as per plan).
        The user can clear manually or restart the app.
        """
        import os
        # 1. Save current session before switching
        try:
            self._session.save()
        except Exception:
            logger.exception("Failed to save session before workspace switch.")

        # 2. Re-create persistence managers at the new root
        self._session = SessionManager(workspace_root=path)
        self._cache = CacheManager(self._session.cache_dir)

        # 3. Update controllers with new session reference
        self._pipeline_ctrl._session = self._session
        self._batch_ctrl._session = self._session
        self._settings_ctrl._session = self._session

        # 4. Update workspace manager
        self._ws_mgr = WorkspaceManager(path)

        # 5. Update window title
        ws_name = os.path.basename(path)
        self.setWindowTitle(f"PyASL - {ws_name}")

        # 6. Refresh Recent Workspaces submenu
        self._refresh_recent_menu()

        logger.info("Switched workspace to: %s", path)
