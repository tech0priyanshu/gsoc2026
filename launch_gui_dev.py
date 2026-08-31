"""
launch_gui_dev.py
-----------------
Hot-reload development launcher for the PyASL Pipeline GUI.

Runs launch_gui.py as a child process and watches ``pyasl/gui/`` for
file changes (.py, .qss).  When a change is detected the GUI is killed
and restarted automatically -- no manual restart required.

Usage
-----
    python launch_gui_dev.py              # watchdog-based (recommended)
    python launch_gui_dev.py --poll       # fallback polling (no watchdog)
    python launch_gui_dev.py --debounce 2 # seconds to wait before restart

Requirements
------------
    pip install watchdog          (optional -- falls back to polling)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

# -- paths -----------------------------------------------------------------
HERE = Path(__file__).resolve().parent
LAUNCH_SCRIPT = HERE / "launch_gui.py"
WATCH_DIRS: list[Path] = [
    HERE / "pyasl" / "gui",
    HERE / "pyasl" / "pipeline",
    HERE / "pyasl" / "pipelines",
    HERE / "pyasl" / "modules",
]
WATCH_EXTENSIONS = {".py", ".qss", ".yaml", ".json"}

# -- ANSI colours (Windows 10+ terminals support these) --------------------
CYAN = "\033[96m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def _banner() -> None:
    print(f"""
{CYAN}{'='*60}
  [HOT-RELOAD]  PyASL GUI -- Dev Server
{'='*60}{RESET}
  Watching:     {', '.join(str(d.relative_to(HERE)) for d in WATCH_DIRS)}
  Extensions:   {', '.join(sorted(WATCH_EXTENSIONS))}
  Entry point:  {LAUNCH_SCRIPT.name}

  {DIM}Save any watched file to trigger an automatic restart.{RESET}
  {DIM}Press Ctrl+C to stop.{RESET}
""")


# -- subprocess management -------------------------------------------------
class GUIProcess:
    """Manages the child GUI process."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            self.stop()
        print(f"{GREEN}>>  Starting GUI ...{RESET}")
        self._proc = subprocess.Popen(
            [sys.executable, str(LAUNCH_SCRIPT)],
            cwd=str(HERE),
        )

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is not None:
            # already exited
            self._proc = None
            return
        print(f"{YELLOW}[]  Stopping GUI (pid {self._proc.pid}) ...{RESET}")
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=2)
        except OSError:
            pass
        self._proc = None

    def restart(self) -> None:
        self.stop()
        self.start()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


# -- file-change detection -------------------------------------------------
def _should_watch(path: str) -> bool:
    """Return True if the file extension is one we care about."""
    return Path(path).suffix.lower() in WATCH_EXTENSIONS


# -- watchdog-based watcher ------------------------------------------------
def _run_watchdog(gui: GUIProcess, debounce: float) -> None:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent

    last_restart = 0.0
    lock = threading.Lock()

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            nonlocal last_restart
            if event.is_directory:
                return
            src = event.src_path
            if not _should_watch(src):
                return
            # ignore __pycache__
            if "__pycache__" in src:
                return
            with lock:
                now = time.time()
                if now - last_restart < debounce:
                    return
                last_restart = now
            rel = Path(src).relative_to(HERE)
            print(f"\n{YELLOW}~~  Change detected: {rel}{RESET}")
            gui.restart()

    observer = Observer()
    handler = _Handler()
    for d in WATCH_DIRS:
        if d.is_dir():
            observer.schedule(handler, str(d), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


# -- polling-based watcher (fallback) --------------------------------------
def _collect_mtimes() -> dict[str, float]:
    mtimes: dict[str, float] = {}
    for d in WATCH_DIRS:
        if not d.is_dir():
            continue
        for root, _dirs, files in os.walk(d):
            if "__pycache__" in root:
                continue
            for f in files:
                full = os.path.join(root, f)
                if _should_watch(full):
                    try:
                        mtimes[full] = os.path.getmtime(full)
                    except OSError:
                        pass
    return mtimes


def _run_polling(gui: GUIProcess, debounce: float, interval: float = 1.0) -> None:
    print(f"{DIM}  (Using polling watcher -- install watchdog for better perf){RESET}\n")
    last_mtimes = _collect_mtimes()

    try:
        while True:
            time.sleep(interval)
            new_mtimes = _collect_mtimes()
            changed: list[str] = []

            for path, mtime in new_mtimes.items():
                if path not in last_mtimes or last_mtimes[path] < mtime:
                    changed.append(path)

            # detect deletions
            for path in set(last_mtimes) - set(new_mtimes):
                changed.append(path)

            if changed:
                for c in changed[:5]:
                    rel = Path(c).relative_to(HERE)
                    print(f"{YELLOW}~~  Changed: {rel}{RESET}")
                if len(changed) > 5:
                    print(f"{DIM}   ... and {len(changed) - 5} more{RESET}")
                gui.restart()
                time.sleep(debounce)

            last_mtimes = new_mtimes
    except KeyboardInterrupt:
        pass


# -- main ------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hot-reload dev launcher for PyASL GUI"
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Use polling instead of watchdog (no extra dependency)",
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=1.5,
        help="Seconds to wait before restarting after a change (default: 1.5)",
    )
    args = parser.parse_args()

    _banner()

    gui = GUIProcess()
    gui.start()

    try:
        if args.poll:
            _run_polling(gui, args.debounce)
        else:
            try:
                import watchdog  # noqa: F401
                _run_watchdog(gui, args.debounce)
            except ImportError:
                print(
                    f"{YELLOW}!  watchdog not installed -- falling back to polling.{RESET}"
                )
                print(f"{DIM}   Install for better perf: pip install watchdog{RESET}\n")
                _run_polling(gui, args.debounce)
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n{RED}[STOP]  Shutting down ...{RESET}")
        gui.stop()
        print(f"{DIM}   Bye!{RESET}")


if __name__ == "__main__":
    main()
