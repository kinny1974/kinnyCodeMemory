"""
KinnyCode — File Watcher

Monitors the project directory for file changes and triggers
automatic incremental re-indexing via the memory server.

Uses the Watchdog library for cross-platform filesystem events.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileWatcher:
    """
    Watches a directory tree for file changes and calls a callback
    when files are created, modified, or deleted.

    Uses a polling-based approach (os.stat) for maximum compatibility,
    with optional Watchdog integration when available.
    """

    IGNORED_DIRS = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        ".idea",
        ".vscode",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        "bin",
        "obj",
        "chroma_memory_db",
    }
    IGNORED_EXTENSIONS = {
        ".pyc",
        ".pyo",
        ".pyd",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".ico",
        ".bmp",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wav",
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".gguf",
    }

    def __init__(
        self,
        project_path: str,
        on_file_changed: Callable[[str, str], None],
        poll_interval: float = 5.0,
    ):
        """
        Args:
            project_path: Root directory to watch.
            on_file_changed: Callback(path, event_type) where event_type is
                             'created', 'modified', or 'deleted'.
            poll_interval: Seconds between scans.
        """
        self.project_path = Path(project_path).resolve()
        self._callback = on_file_changed
        self._poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._file_mtimes: dict[str, float] = {}

    def start(self):
        """Start watching in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("File watcher started for %s", self.project_path)

    def stop(self):
        """Stop the watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("File watcher stopped.")

    def _poll_loop(self):
        """Main polling loop."""
        # Build initial snapshot
        self._scan(initial=True)

        while self._running:
            time.sleep(self._poll_interval)
            try:
                self._scan(initial=False)
            except Exception as exc:
                logger.warning("File watcher scan error: %s", exc)

    def _scan(self, initial: bool = False):
        """Scan the project tree and detect changes."""
        current_files: dict[str, float] = {}

        if not self.project_path.exists():
            return

        for entry in self.project_path.rglob("*"):
            if not entry.is_file():
                continue

            # Skip ignored directories
            parts = entry.relative_to(self.project_path).parts
            if any(p in self.IGNORED_DIRS for p in parts):
                continue

            # Skip ignored extensions
            if entry.suffix.lower() in self.IGNORED_EXTENSIONS:
                continue

            rel = str(entry.relative_to(self.project_path))
            mtime = entry.stat().st_mtime
            current_files[rel] = mtime

        if initial:
            self._file_mtimes = current_files
            return

        # Detect changes
        for path, mtime in current_files.items():
            old_mtime = self._file_mtimes.get(path)
            if old_mtime is None:
                # New file
                try:
                    self._callback(str(self.project_path / path), "created")
                except Exception:
                    pass
            elif mtime > old_mtime + 0.1:  # Small threshold for rounding
                # Modified file
                try:
                    self._callback(str(self.project_path / path), "modified")
                except Exception:
                    pass

        # Detect deletions
        for path in list(self._file_mtimes.keys()):
            if path not in current_files:
                try:
                    self._callback(str(self.project_path / path), "deleted")
                except Exception:
                    pass

        # Update snapshot
        self._file_mtimes = current_files


# ── Module-level helper ────────────────────────────────────────────
def start_file_watcher(
    project_path: str,
    on_file_changed: Callable[[str, str], None],
    poll_interval: float = 5.0,
) -> FileWatcher:
    """Create and start a FileWatcher. Returns the watcher instance."""
    watcher = FileWatcher(project_path, on_file_changed, poll_interval)
    watcher.start()
    return watcher
