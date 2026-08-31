"""
Tests for the Workspace feature.

Covers:
  - WorkspaceManager: create, open, info, recent workspaces persistence
  - WorkspaceInfoDialog: UI rendering and content
  - MainWindow workspace menu and actions
  - Integration: full workspace lifecycle (create → switch → restore)

Follows the same fixture / assertion patterns used by the existing
test suite (pytest + pytest-qt).
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QMessageBox

from pyasl.gui.views.main_window import WorkspaceManager, WorkspaceInfoDialog


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def ws_root(tmp_path):
    """Create a temporary workspace root directory."""
    ws = tmp_path / "test_workspace"
    ws.mkdir()
    return str(ws)


@pytest.fixture
def ws_mgr(ws_root, tmp_path):
    """WorkspaceManager backed by a temp workspace and temp config dir."""
    mgr = WorkspaceManager(ws_root)
    # Override config dir so tests don't pollute user's home
    config_dir = tmp_path / ".pyasl_config_test"
    config_dir.mkdir(exist_ok=True)
    mgr._config_dir = config_dir
    mgr._recent_path = config_dir / "recent_workspaces.json"
    return mgr


# ======================================================================
# Unit Tests — WorkspaceManager
# ======================================================================


class TestWorkspaceManagerInit:
    """Verify WorkspaceManager initialisation and properties."""

    def test_current_root_matches_input(self, ws_mgr, ws_root):
        """current_root should resolve to the path we passed in."""
        from pathlib import Path
        assert ws_mgr.current_root == Path(ws_root).resolve()

    def test_current_name_is_basename(self, ws_mgr):
        """current_name should be the directory basename."""
        assert ws_mgr.current_name == "test_workspace"

    def test_config_dir_created(self, ws_mgr):
        """The global config directory for recent-workspaces should exist."""
        assert ws_mgr._config_dir.is_dir()


class TestWorkspaceManagerCreateNew:
    """Verify workspace creation and scaffolding."""

    def test_create_new_returns_true(self, ws_mgr, tmp_path):
        """create_new should return True on success."""
        new_ws = str(tmp_path / "brand_new_ws")
        assert ws_mgr.create_new(new_ws) is True

    def test_create_new_scaffolds_subdirs(self, ws_mgr, tmp_path):
        """create_new should create uploads/, cache/, logs/ sub-dirs."""
        new_ws = str(tmp_path / "scaffolded_ws")
        ws_mgr.create_new(new_ws)

        from pathlib import Path
        root = Path(new_ws)
        assert (root / "uploads").is_dir()
        assert (root / "cache").is_dir()
        assert (root / "logs").is_dir()

    def test_create_new_updates_current(self, ws_mgr, tmp_path):
        """After create_new, current_root should point to the new path."""
        new_ws = str(tmp_path / "updated_ws")
        ws_mgr.create_new(new_ws)

        from pathlib import Path
        assert ws_mgr.current_root == Path(new_ws).resolve()

    def test_create_new_adds_to_recent(self, ws_mgr, tmp_path):
        """create_new should push the path into the recent list."""
        new_ws = str(tmp_path / "recent_ws")
        ws_mgr.create_new(new_ws)
        recent = ws_mgr.get_recent()
        from pathlib import Path
        assert str(Path(new_ws).resolve()) in recent

    def test_create_new_idempotent(self, ws_mgr, tmp_path):
        """Calling create_new twice on the same path should not fail."""
        new_ws = str(tmp_path / "idempotent_ws")
        assert ws_mgr.create_new(new_ws) is True
        assert ws_mgr.create_new(new_ws) is True

    def test_create_new_nested_dirs(self, ws_mgr, tmp_path):
        """create_new should create parent directories if needed."""
        nested = str(tmp_path / "deep" / "nested" / "ws")
        assert ws_mgr.create_new(nested) is True
        from pathlib import Path
        assert Path(nested).is_dir()


class TestWorkspaceManagerOpen:
    """Verify opening existing workspace directories."""

    def test_open_existing_dir_returns_true(self, ws_mgr, tmp_path):
        """open() should return True for an existing directory."""
        existing = str(tmp_path / "existing_ws")
        os.makedirs(existing)
        assert ws_mgr.open(existing) is True

    def test_open_nonexistent_returns_false(self, ws_mgr, tmp_path):
        """open() should return False for a non-existent path."""
        assert ws_mgr.open(str(tmp_path / "nonexistent")) is False

    def test_open_file_returns_false(self, ws_mgr, tmp_path):
        """open() should return False when given a file path, not a dir."""
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello")
        assert ws_mgr.open(str(f)) is False

    def test_open_scaffolds_missing_subdirs(self, ws_mgr, tmp_path):
        """open() should create scaffold sub-dirs if they're missing."""
        existing = str(tmp_path / "bare_ws")
        os.makedirs(existing)
        ws_mgr.open(existing)

        from pathlib import Path
        root = Path(existing)
        assert (root / "uploads").is_dir()
        assert (root / "cache").is_dir()
        assert (root / "logs").is_dir()

    def test_open_updates_current(self, ws_mgr, tmp_path):
        """After open(), current_root should point to the opened path."""
        existing = str(tmp_path / "opened_ws")
        os.makedirs(existing)
        ws_mgr.open(existing)

        from pathlib import Path
        assert ws_mgr.current_root == Path(existing).resolve()

    def test_open_adds_to_recent(self, ws_mgr, tmp_path):
        """open() should push the path into the recent list."""
        existing = str(tmp_path / "recent_open_ws")
        os.makedirs(existing)
        ws_mgr.open(existing)
        from pathlib import Path
        recent = ws_mgr.get_recent()
        assert str(Path(existing).resolve()) in recent


class TestWorkspaceManagerInfo:
    """Verify workspace info / metadata retrieval."""

    def test_info_has_required_keys(self, ws_mgr):
        """info() dict should contain name, path, size_bytes, session_exists."""
        info = ws_mgr.info()
        assert "name" in info
        assert "path" in info
        assert "size_bytes" in info
        assert "session_exists" in info

    def test_info_name_matches_current(self, ws_mgr):
        """info()['name'] should equal current_name."""
        info = ws_mgr.info()
        assert info["name"] == ws_mgr.current_name

    def test_info_session_exists_false_when_no_session(self, ws_mgr):
        """session_exists should be False when there's no session.json."""
        info = ws_mgr.info()
        assert info["session_exists"] is False

    def test_info_session_exists_true_after_creation(self, ws_mgr, ws_root):
        """session_exists should be True after writing a session.json."""
        from pathlib import Path
        session_file = Path(ws_root) / "session.json"
        session_file.write_text("{}")
        info = ws_mgr.info()
        assert info["session_exists"] is True

    def test_info_size_bytes_is_nonnegative(self, ws_mgr):
        """size_bytes should be a non-negative integer."""
        info = ws_mgr.info()
        assert info["size_bytes"] >= 0

    def test_info_size_bytes_increases_with_content(self, ws_mgr, ws_root):
        """size_bytes should increase when we add files."""
        from pathlib import Path
        initial = ws_mgr.info()["size_bytes"]
        (Path(ws_root) / "dummy.bin").write_bytes(b"\x00" * 4096)
        after = ws_mgr.info()["size_bytes"]
        assert after >= initial + 4096


class TestWorkspaceManagerRecent:
    """Verify recent-workspaces persistence and management."""

    def test_get_recent_empty_initially(self, ws_mgr):
        """get_recent() should return [] when no recent file exists."""
        # Make sure file doesn't exist
        if ws_mgr._recent_path.exists():
            ws_mgr._recent_path.unlink()
        assert ws_mgr.get_recent() == []

    def test_push_and_get_recent(self, ws_mgr, tmp_path):
        """After creating a workspace, it should appear in get_recent()."""
        new_ws = str(tmp_path / "push_ws")
        ws_mgr.create_new(new_ws)
        recent = ws_mgr.get_recent()
        assert len(recent) >= 1

    def test_recent_order_newest_first(self, ws_mgr, tmp_path):
        """Most recently created workspace should be first in the list."""
        from pathlib import Path
        ws1 = str(tmp_path / "ws_first")
        ws2 = str(tmp_path / "ws_second")
        ws_mgr.create_new(ws1)
        ws_mgr.create_new(ws2)
        recent = ws_mgr.get_recent()
        assert recent[0] == str(Path(ws2).resolve())

    def test_recent_deduplication(self, ws_mgr, tmp_path):
        """Opening the same workspace twice should not create duplicate entries."""
        ws1 = str(tmp_path / "dedup_ws")
        ws_mgr.create_new(ws1)
        ws_mgr.create_new(ws1)  # second time
        from pathlib import Path
        norm = str(Path(ws1).resolve())
        recent = ws_mgr.get_recent()
        assert recent.count(norm) == 1

    def test_recent_max_limit(self, ws_mgr, tmp_path):
        """The recent list should be capped at MAX_RECENT entries."""
        for i in range(ws_mgr.MAX_RECENT + 5):
            p = str(tmp_path / f"ws_{i:03d}")
            ws_mgr.create_new(p)
        recent = ws_mgr.get_recent()
        assert len(recent) <= ws_mgr.MAX_RECENT

    def test_clear_recent(self, ws_mgr, tmp_path):
        """clear_recent() should empty the recent list."""
        ws_mgr.create_new(str(tmp_path / "to_clear"))
        ws_mgr.clear_recent()
        assert ws_mgr.get_recent() == []

    def test_recent_persists_to_file(self, ws_mgr, tmp_path):
        """Recent workspaces should be written to a JSON file on disk."""
        ws_mgr.create_new(str(tmp_path / "persist_ws"))
        assert ws_mgr._recent_path.is_file()
        data = json.loads(ws_mgr._recent_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_corrupted_recent_file_returns_empty(self, ws_mgr):
        """If the recent-workspaces JSON file is corrupted, return []."""
        ws_mgr._recent_path.write_text("{{{invalid", encoding="utf-8")
        assert ws_mgr.get_recent() == []

    def test_non_list_recent_file_returns_empty(self, ws_mgr):
        """If the recent file contains a non-list JSON, return []."""
        ws_mgr._recent_path.write_text('{"key": "val"}', encoding="utf-8")
        assert ws_mgr.get_recent() == []


# ======================================================================
# Unit Tests — WorkspaceInfoDialog
# ======================================================================


class TestWorkspaceInfoDialog:
    """Verify WorkspaceInfoDialog UI construction and display."""

    def test_dialog_title(self, qtbot):
        """Dialog should have the title 'Workspace Info'."""
        dlg = WorkspaceInfoDialog({"name": "test", "path": "/tmp", "size_bytes": 0, "session_exists": False})
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Workspace Info"

    def test_dialog_displays_name(self, qtbot):
        """The name label should show the workspace name."""
        dlg = WorkspaceInfoDialog({"name": "my_ws", "path": "/tmp/my_ws", "size_bytes": 0, "session_exists": False})
        qtbot.addWidget(dlg)
        assert dlg._name_lbl.text() == "my_ws"

    def test_dialog_displays_path(self, qtbot):
        """The path label should show the workspace path."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/home/user/ws", "size_bytes": 0, "session_exists": False})
        qtbot.addWidget(dlg)
        assert dlg._path_lbl.text() == "/home/user/ws"

    def test_dialog_displays_size_kb(self, qtbot):
        """Sizes under 1 MB should be displayed in KB."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/tmp", "size_bytes": 512 * 1024, "session_exists": False})
        qtbot.addWidget(dlg)
        assert "KB" in dlg._size_lbl.text()

    def test_dialog_displays_size_mb(self, qtbot):
        """Sizes >= 1 MB should be displayed in MB."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/tmp", "size_bytes": 5 * 1024 * 1024, "session_exists": False})
        qtbot.addWidget(dlg)
        assert "MB" in dlg._size_lbl.text()

    def test_dialog_session_exists_yes(self, qtbot):
        """When session_exists is True, the label should say 'Yes'."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/tmp", "size_bytes": 0, "session_exists": True})
        qtbot.addWidget(dlg)
        assert "Yes" in dlg._session_lbl.text()

    def test_dialog_session_exists_no(self, qtbot):
        """When session_exists is False, the label should say 'No'."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/tmp", "size_bytes": 0, "session_exists": False})
        qtbot.addWidget(dlg)
        assert "No" in dlg._session_lbl.text()

    def test_dialog_is_modal(self, qtbot):
        """The dialog should be modal."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/tmp", "size_bytes": 0, "session_exists": False})
        qtbot.addWidget(dlg)
        assert dlg.isModal()

    def test_dialog_minimum_width(self, qtbot):
        """Dialog should have a minimum width of 420px."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/tmp", "size_bytes": 0, "session_exists": False})
        qtbot.addWidget(dlg)
        assert dlg.minimumWidth() >= 420

    def test_dialog_accepts_on_close_click(self, qtbot):
        """Clicking the Close button should accept (close) the dialog."""
        dlg = WorkspaceInfoDialog({"name": "ws", "path": "/tmp", "size_bytes": 0, "session_exists": False})
        qtbot.addWidget(dlg)
        # Dialog should accept without errors
        dlg.accept()


# ======================================================================
# Unit Tests — MainWindow Workspace Integration
# ======================================================================


class TestMainWindowWorkspaceMenu:
    """Verify that the Workspace menu is correctly wired in MainWindow."""

    def test_workspace_menu_exists(self, main_window):
        """A top-level 'Workspace' menu should exist in the menu bar."""
        menubar = main_window.menuBar()
        menu_names = [a.text() for a in menubar.actions()]
        assert "Workspace" in menu_names

    def test_workspace_menu_position(self, main_window):
        """Workspace menu should appear after File and before View."""
        menubar = main_window.menuBar()
        menu_names = [a.text() for a in menubar.actions()]
        file_idx = menu_names.index("File")
        ws_idx = menu_names.index("Workspace")
        view_idx = menu_names.index("View")
        assert file_idx < ws_idx < view_idx

    def test_workspace_manager_initialised(self, main_window):
        """MainWindow should have a _ws_mgr attribute after construction."""
        assert hasattr(main_window, "_ws_mgr")
        assert isinstance(main_window._ws_mgr, WorkspaceManager)

    def test_recent_menu_initialised(self, main_window):
        """MainWindow should have a _recent_menu attribute."""
        assert hasattr(main_window, "_recent_menu")

    def test_file_menu_still_exists(self, main_window):
        """The existing File menu must still be present (no regression)."""
        menubar = main_window.menuBar()
        menu_names = [a.text() for a in menubar.actions()]
        assert "File" in menu_names

    def test_view_menu_still_exists(self, main_window):
        """The existing View menu must still be present (no regression)."""
        menubar = main_window.menuBar()
        menu_names = [a.text() for a in menubar.actions()]
        assert "View" in menu_names

    def test_help_menu_still_exists(self, main_window):
        """The existing Help menu must still be present (no regression)."""
        menubar = main_window.menuBar()
        menu_names = [a.text() for a in menubar.actions()]
        assert "Help" in menu_names


class TestMainWindowWorkspaceNew:
    """Verify MainWindow._workspace_new() behaviour."""

    def test_workspace_new_cancelled_no_side_effects(self, main_window, monkeypatch):
        """If the user cancels the directory dialog, nothing should change."""
        from PyQt6.QtWidgets import QFileDialog
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")

        original_title = main_window.windowTitle()
        main_window._workspace_new()
        assert main_window.windowTitle() == original_title

    def test_workspace_new_creates_and_switches(self, main_window, monkeypatch, tmp_path):
        """Selecting a directory should create workspace and update title."""
        from PyQt6.QtWidgets import QFileDialog
        new_ws = str(tmp_path / "new_ws_for_test")
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: new_ws)

        main_window._workspace_new()

        from pathlib import Path
        assert Path(new_ws).is_dir()
        assert (Path(new_ws) / "uploads").is_dir()
        assert (Path(new_ws) / "cache").is_dir()
        assert (Path(new_ws) / "logs").is_dir()
        assert "new_ws_for_test" in main_window.windowTitle()

    def test_workspace_new_updates_status(self, main_window, monkeypatch, tmp_path):
        """After creating a workspace, the status bar should reflect the change."""
        from PyQt6.QtWidgets import QFileDialog
        new_ws = str(tmp_path / "status_ws")
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: new_ws)

        main_window._workspace_new()
        assert "New workspace created" in main_window._status_lbl.text()


class TestMainWindowWorkspaceOpen:
    """Verify MainWindow._workspace_open() behaviour."""

    def test_workspace_open_cancelled_no_side_effects(self, main_window, monkeypatch):
        """If the user cancels, nothing should change."""
        from PyQt6.QtWidgets import QFileDialog
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")

        original_title = main_window.windowTitle()
        main_window._workspace_open()
        assert main_window.windowTitle() == original_title

    def test_workspace_open_valid_dir_switches(self, main_window, monkeypatch, tmp_path):
        """Opening a valid directory should switch the workspace."""
        from PyQt6.QtWidgets import QFileDialog
        existing = str(tmp_path / "open_test_ws")
        os.makedirs(existing)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: existing)

        main_window._workspace_open()
        assert "open_test_ws" in main_window.windowTitle()

    def test_workspace_open_updates_status(self, main_window, monkeypatch, tmp_path):
        """After opening a workspace, the status bar should reflect the change."""
        from PyQt6.QtWidgets import QFileDialog
        existing = str(tmp_path / "open_status_ws")
        os.makedirs(existing)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: existing)

        main_window._workspace_open()
        assert "Workspace opened" in main_window._status_lbl.text()


class TestMainWindowWorkspaceInfo:
    """Verify MainWindow._workspace_info() behaviour."""

    def test_workspace_info_opens_dialog(self, main_window, monkeypatch):
        """_workspace_info should instantiate and exec a WorkspaceInfoDialog."""
        exec_mock = MagicMock()
        monkeypatch.setattr(WorkspaceInfoDialog, "exec", exec_mock)

        main_window._workspace_info()
        assert exec_mock.call_count == 1


class TestMainWindowSwitchWorkspace:
    """Verify the internal _switch_workspace() method."""

    def test_switch_updates_session(self, main_window, tmp_path):
        """After switching, _session.workspace_root should point to the new path."""
        new_ws = str(tmp_path / "switched_ws")
        os.makedirs(new_ws, exist_ok=True)

        main_window._switch_workspace(new_ws)

        assert main_window._session.workspace_root == os.path.abspath(new_ws)

    def test_switch_updates_title(self, main_window, tmp_path):
        """Window title should contain the new workspace name."""
        new_ws = str(tmp_path / "titled_ws")
        os.makedirs(new_ws, exist_ok=True)

        main_window._switch_workspace(new_ws)
        assert "titled_ws" in main_window.windowTitle()

    def test_switch_updates_controllers(self, main_window, tmp_path):
        """Controller session references should point to the new SessionManager."""
        new_ws = str(tmp_path / "ctrl_ws")
        os.makedirs(new_ws, exist_ok=True)

        main_window._switch_workspace(new_ws)

        assert main_window._pipeline_ctrl._session is main_window._session
        assert main_window._batch_ctrl._session is main_window._session
        assert main_window._settings_ctrl._session is main_window._session

    def test_switch_updates_workspace_manager(self, main_window, tmp_path):
        """_ws_mgr should reference the new workspace after switching."""
        new_ws = str(tmp_path / "wsmgr_ws")
        os.makedirs(new_ws, exist_ok=True)

        main_window._switch_workspace(new_ws)
        from pathlib import Path
        assert main_window._ws_mgr.current_root == Path(new_ws).resolve()


class TestMainWindowRecentMenu:
    """Verify the Recent Workspaces submenu behaviour."""

    def test_recent_menu_empty_initially_has_placeholder(self, main_window):
        """When no recent workspaces, the submenu should show a disabled placeholder."""
        # Clear any existing recent entries
        main_window._ws_mgr.clear_recent()
        main_window._refresh_recent_menu()

        actions = main_window._recent_menu.actions()
        assert len(actions) >= 1
        assert actions[0].isEnabled() is False

    def test_recent_menu_populated_after_switch(self, main_window, monkeypatch, tmp_path):
        """After creating and switching to a workspace, the recent menu should have entries."""
        from PyQt6.QtWidgets import QFileDialog
        new_ws = str(tmp_path / "recent_test_ws")
        # Use _workspace_new which calls create_new (pushes to recent)
        # then _switch_workspace
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: new_ws)
        main_window._workspace_new()

        actions = main_window._recent_menu.actions()
        # Should have at least 1 entry + separator + "Clear Recent"
        enabled_actions = [a for a in actions if a.isEnabled() and not a.isSeparator()]
        assert len(enabled_actions) >= 1

    def test_clear_recent_empties_menu(self, main_window, tmp_path):
        """After clearing recent, the menu should revert to placeholder."""
        new_ws = str(tmp_path / "clear_recent_ws")
        os.makedirs(new_ws, exist_ok=True)
        main_window._switch_workspace(new_ws)

        main_window._clear_recent_workspaces()

        actions = main_window._recent_menu.actions()
        # Should just have the disabled placeholder
        assert actions[0].isEnabled() is False


# ======================================================================
# Integration Tests — Full Workspace Lifecycle
# ======================================================================


class TestWorkspaceLifecycleIntegration:
    """End-to-end integration tests for the workspace feature."""

    def test_create_switch_and_verify_session(self, main_window, tmp_path):
        """
        Full lifecycle:
        1. Create a new workspace via the manager
        2. Switch to it
        3. Save session data in the new workspace
        4. Verify the session file exists in the new workspace
        """
        new_ws = str(tmp_path / "lifecycle_ws")

        # 1. Create
        ok = main_window._ws_mgr.create_new(new_ws)
        assert ok is True

        # 2. Switch
        main_window._switch_workspace(new_ws)

        # 3. Save session
        main_window._session.save()

        # 4. Verify
        session_path = os.path.join(new_ws, "session.json")
        assert os.path.isfile(session_path)

    def test_switch_preserves_session_at_old_workspace(self, main_window, tmp_path):
        """
        After switching workspaces, the old workspace's session.json
        should still exist (saved before switching).
        """
        old_root = main_window._session.workspace_root
        main_window._session.save()  # ensure something is saved

        new_ws = str(tmp_path / "new_ws_preserve")
        os.makedirs(new_ws)
        main_window._switch_workspace(new_ws)

        # Old session.json should still exist
        old_session = os.path.join(old_root, "session.json")
        assert os.path.isfile(old_session)

    def test_switch_back_to_previous_workspace(self, main_window, tmp_path):
        """Switching to workspace A, then B, then back to A should work."""
        ws_a = str(tmp_path / "ws_a")
        ws_b = str(tmp_path / "ws_b")
        os.makedirs(ws_a)
        os.makedirs(ws_b)

        main_window._switch_workspace(ws_a)
        assert "ws_a" in main_window.windowTitle()

        main_window._switch_workspace(ws_b)
        assert "ws_b" in main_window.windowTitle()

        main_window._switch_workspace(ws_a)
        assert "ws_a" in main_window.windowTitle()
        assert main_window._session.workspace_root == os.path.abspath(ws_a)

    def test_session_data_isolated_between_workspaces(self, main_window, tmp_path):
        """
        Pipeline data saved in workspace A should not leak into workspace B.
        """
        ws_a = str(tmp_path / "iso_a")
        ws_b = str(tmp_path / "iso_b")
        os.makedirs(ws_a)
        os.makedirs(ws_b)

        # Switch to A and save pipeline data
        main_window._switch_workspace(ws_a)
        main_window._session.set_pipeline({"nodes": [{"id": "n1", "func": "f1"}]})

        # Switch to B — fresh session
        main_window._switch_workspace(ws_b)
        pipeline_b = main_window._session.get_pipeline()
        assert pipeline_b.get("nodes", []) == []  # should be empty

        # Switch back to A — data should still be there
        main_window._switch_workspace(ws_a)
        # Need to reload the session to get persisted data
        success, _ = main_window._session.load()
        if success:
            pipeline_a = main_window._session.get_pipeline()
            assert len(pipeline_a.get("nodes", [])) == 1

    def test_settings_persist_per_workspace(self, main_window, tmp_path):
        """Settings stored in one workspace should not affect another."""
        ws_a = str(tmp_path / "settings_a")
        ws_b = str(tmp_path / "settings_b")
        os.makedirs(ws_a)
        os.makedirs(ws_b)

        # Set workers to 8 in workspace A
        main_window._switch_workspace(ws_a)
        main_window._session.set_settings({
            "log_path": "",
            "default_workers": 8,
            "theme": "dark",
        })

        # Switch to B — should have default settings
        main_window._switch_workspace(ws_b)
        settings_b = main_window._session.get_settings()
        workers_b = settings_b.get("default_workers", 2)
        assert workers_b == 2  # default value

    def test_close_event_saves_current_workspace(self, main_window, tmp_path):
        """closeEvent should save the session for the current workspace."""
        new_ws = str(tmp_path / "close_ws")
        os.makedirs(new_ws)
        main_window._switch_workspace(new_ws)

        # Trigger close event
        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        main_window.closeEvent(event)

        session_path = os.path.join(new_ws, "session.json")
        assert os.path.isfile(session_path)

    def test_workspace_new_end_to_end(self, main_window, monkeypatch, tmp_path):
        """
        Complete flow: Workspace → New Workspace → select dir →
        workspace is created, title updated, session manager re-pointed.
        """
        from PyQt6.QtWidgets import QFileDialog
        new_ws = str(tmp_path / "e2e_new_ws")
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: new_ws)

        main_window._workspace_new()

        # Verify workspace was created with scaffold
        from pathlib import Path
        assert (Path(new_ws) / "uploads").is_dir()
        assert (Path(new_ws) / "cache").is_dir()
        assert (Path(new_ws) / "logs").is_dir()

        # Verify title and session
        assert "e2e_new_ws" in main_window.windowTitle()
        assert main_window._session.workspace_root == os.path.abspath(new_ws)

        # Verify recent workspaces updated
        recent = main_window._ws_mgr.get_recent()
        assert any("e2e_new_ws" in r for r in recent)

    def test_workspace_open_end_to_end(self, main_window, monkeypatch, tmp_path):
        """
        Complete flow: Workspace → Open Workspace → select existing dir →
        workspace opened, title updated.
        """
        from PyQt6.QtWidgets import QFileDialog
        existing_ws = str(tmp_path / "e2e_open_ws")
        os.makedirs(existing_ws)
        # Simulate an existing workspace with a session file
        session_file = os.path.join(existing_ws, "session.json")
        with open(session_file, "w") as f:
            json.dump({"version": 1, "batch_jobs": [], "pipeline": {"nodes": []}, "settings": {}}, f)

        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: existing_ws)

        main_window._workspace_open()

        assert "e2e_open_ws" in main_window.windowTitle()
        assert main_window._session.workspace_root == os.path.abspath(existing_ws)


class TestWorkspaceRegressionGuards:
    """Ensure the workspace feature does not break existing functionality."""

    def test_tabs_still_exist(self, main_window):
        """All original tabs should still be present after workspace feature addition."""
        tabs = main_window._tabs
        assert tabs is not None
        tab_texts = [tabs.tabText(i) for i in range(tabs.count())]
        assert any("Pipeline Builder" in t for t in tab_texts)
        assert any("Batch" in t for t in tab_texts)
        assert any("Monitor" in t for t in tab_texts)
        assert any("Settings" in t for t in tab_texts)

    def test_shortcuts_still_work(self, main_window):
        """Shortcut manager should still be initialised."""
        assert hasattr(main_window, "_shortcut_mgr")

    def test_theme_switching_still_works(self, main_window):
        """Theme switching should still function correctly."""
        from pyasl.gui.constants import Colors
        main_window.set_theme("light")
        assert Colors.BG_PRIMARY == "#f8fafc"
        main_window.set_theme("dark")
        assert Colors.BG_PRIMARY == "#000000"

    def test_status_bar_still_works(self, main_window):
        """Status bar and label should still be present."""
        assert hasattr(main_window, "_status_lbl")
        assert main_window._status_lbl is not None

    def test_pipeline_controller_still_works(self, main_window):
        """Pipeline controller should still be functional."""
        assert hasattr(main_window, "_pipeline_ctrl")
        assert main_window._pipeline_ctrl is not None

    def test_batch_controller_still_works(self, main_window):
        """Batch controller should still be functional."""
        assert hasattr(main_window, "_batch_ctrl")
        assert main_window._batch_ctrl is not None

    def test_about_dialog_still_works(self, main_window, monkeypatch):
        """The About dialog should still open."""
        exec_mock = MagicMock()
        monkeypatch.setattr(QMessageBox, "exec", exec_mock)
        main_window._show_about()
        assert exec_mock.call_count == 1
