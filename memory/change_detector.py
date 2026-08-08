"""
KinnyCode — Change Detector (Sprint 1 & 2)

Strategy-pattern change detection with dual validation:
  Level 1 (fast):   mtime + size via os.stat() — O(1)
  Level 2 (precise): SHA256 incremental via 64KB blocks — avoids full rehash

Components:
  - HashCalculator:    Computes SHA256 with optional block-level caching
  - DedupLock:         Prevents duplicate reindex events for the same file
  - IChangeDetector:   Abstract interface for polling or watchdog backends
  - PollingChangeDetector:  Polling-based implementation (default)
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from .hash_cache import HashCache
from .ignore_patterns import IgnorePatterns

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

BLOCK_SIZE = 65536  # 64KB blocks for chunk-based hashing
DEDUP_LOCK_TIMEOUT = 30  # seconds before lock auto-releases


class HashCalculator:
    """
    Computes SHA256 hashes with optional block-level granularity.

    Usage:
        calc = HashCalculator()
        full_hash = calc.compute("src/main.py")
        block_hashes = calc.compute_with_blocks("src/main.py")
    """

    @staticmethod
    def compute(file_path: str) -> str | None:
        """
        Compute full SHA256 hex digest of a file.

        Args:
            file_path: Absolute or relative path to the file.

        Returns:
            SHA256 hex digest string, or None on error.
        """
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(BLOCK_SIZE), b""):
                    h.update(chunk)
            return h.hexdigest()
        except OSError as e:
            logger.warning("HashCalculator: failed to hash %s: %s", file_path, e)
            return None
        except Exception as e:
            logger.error("HashCalculator: unexpected error hashing %s: %s", file_path, e)
            return None

    @staticmethod
    def compute_with_blocks(
        file_path: str, cached_block_hashes: dict[str, str] | None = None
    ) -> tuple[str, dict[str, str]] | None:
        """
        Compute SHA256 with per-block granularity.

        Returns:
            Tuple of (full_hash, block_hashes_dict) or None on error.
            block_hashes_dict = { "0": "block_0_hash", "65536": "block_1_hash", ... }
        """
        try:
            block_hashes = {}
            full_hasher = hashlib.sha256()
            offset = 0

            with open(file_path, "rb") as f:
                while True:
                    block = f.read(BLOCK_SIZE)
                    if not block:
                        break

                    block_hash = hashlib.sha256(block).hexdigest()
                    block_hashes[str(offset)] = block_hash
                    full_hasher.update(block)
                    offset += len(block)

            return full_hasher.hexdigest(), block_hashes
        except OSError as e:
            logger.warning(
                "HashCalculator: failed to compute block hashes for %s: %s", file_path, e
            )
            return None
        except Exception as e:
            logger.error(
                "HashCalculator: unexpected error computing block hashes for %s: %s", file_path, e
            )
            return None

    @staticmethod
    def compute_content(content: str) -> str:
        """Compute SHA256 hex digest of a string (for server-side use)."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_stat(file_path: str) -> tuple[float, int] | None:
        """
        Get mtime and size of a file in one stat call.

        Returns:
            Tuple of (mtime, size) or None on error.
        """
        try:
            stat = os.stat(file_path)
            return (stat.st_mtime, stat.st_size)
        except OSError as e:
            logger.warning("HashCalculator: failed to stat %s: %s", file_path, e)
            return None
        except Exception as e:
            logger.error("HashCalculator: unexpected error statting %s: %s", file_path, e)
            return None


class DedupLock:
    """
    Prevents duplicate reindex events for the same file.

    Uses a dict of threading.Lock objects keyed by file_path.
    Supports configurable timeout for auto-release.

    Usage:
        dedup = DedupLock()
        if dedup.acquire("/path/to/file.py"):
            try:
                # Reindex the file
                reindex_file("/path/to/file.py")
            finally:
                dedup.release("/path/to/file.py")
    """

    def __init__(self, timeout: int = DEDUP_LOCK_TIMEOUT):
        self._timeout = timeout
        self._locks: dict[str, threading.Lock] = {}
        self._lock_times: dict[str, float] = {}
        self._global_lock = threading.Lock()

    def acquire(self, file_path: str) -> bool:
        """
        Acquire lock for a file path.

        Returns:
            True if lock acquired, False if another thread holds it
            or the lock is still within the timeout window.
        """
        with self._global_lock:
            # Prune stale locks
            self._prune_stale()

            if file_path in self._locks:
                # Check if lock is still within timeout
                last_time = self._lock_times.get(file_path, 0)
                if time.time() - last_time < self._timeout:
                    logger.debug("DedupLock: duplicate event skipped for %s", file_path)
                    return False
                # Timeout expired or lock held too long — release old lock
                try:
                    self._locks[file_path].release()
                except RuntimeError:
                    pass

        # Try to acquire the lock
        lock = threading.Lock()
        acquired = lock.acquire(blocking=False)
        if acquired:
            with self._global_lock:
                self._locks[file_path] = lock
                self._lock_times[file_path] = time.time()
            logger.debug("DedupLock: acquired for %s", file_path)
            return True
        return False

    def release(self, file_path: str) -> None:
        """Release lock for a file path."""
        with self._global_lock:
            lock = self._locks.pop(file_path, None)
            self._lock_times.pop(file_path, None)
        if lock:
            try:
                lock.release()
            except RuntimeError:
                pass

    def _prune_stale(self) -> None:
        """Remove expired lock entries (must be called with _global_lock held)."""
        now = time.time()
        expired = [path for path, t in self._lock_times.items() if now - t >= self._timeout]
        for path in expired:
            lock = self._locks.pop(path, None)
            self._lock_times.pop(path, None)
            if lock:
                try:
                    lock.release()
                except RuntimeError:
                    pass


class IChangeDetector(ABC):
    """
    Abstract interface for change detection backends.

    Implementations:
        - PollingChangeDetector:  Polls filesystem at intervals
        - WatchdogChangeDetector: Uses watchdog library (Sprint 5)
    """

    @abstractmethod
    def start(self) -> None:
        """Start the change detector."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the change detector."""

    @abstractmethod
    def on_change(self, callback: Callable[[str, str], None]) -> None:
        """
        Register a callback for file change events.

        Args:
            callback: Function(path, event_type) where event_type is
                      'created', 'modified', or 'deleted'.
        """


class PollingChangeDetector(IChangeDetector):
    """
    Polling-based change detector with triple validation:
        1. mtime + size (fast, O(1) via os.stat)
        2. SHA256 hash (precise, only when mtime/size differ)
        3. DedupLock (prevents duplicate processing)

    Usage:
        detector = PollingChangeDetector(
            project_path="/path/to/project",
            cache=HashCache(cache_path),
            ignore_patterns=IgnorePatterns(),
            poll_interval=3.0,
        )
        detector.on_change(self._on_file_changed)
        detector.start()
    """

    def __init__(
        self,
        project_path: str,
        cache: HashCache,
        ignore_patterns: IgnorePatterns,
        poll_interval: float = 3.0,
        dedup_timeout: int = DEDUP_LOCK_TIMEOUT,
    ):
        self.project_path = Path(project_path).resolve()
        self._cache = cache
        self._ignore = ignore_patterns
        self._poll_interval = poll_interval
        self._dedup = DedupLock(timeout=dedup_timeout)

        self._callback: Callable[[str, str], None] | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._snapshot: dict[str, dict] = {}  # rel_path → {mtime, size, sha256}

    def start(self) -> None:
        """Start polling in a background thread."""
        if self._running:
            return
        self._running = True
        self._snapshot = self._build_snapshot(initial=True)
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(
            "PollingChangeDetector started for %s (interval=%.1fs)",
            self.project_path,
            self._poll_interval,
        )

    def stop(self) -> None:
        """Stop the polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("PollingChangeDetector stopped.")

    def on_change(self, callback: Callable[[str, str], None]) -> None:
        """Register change callback."""
        self._callback = callback

    def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            time.sleep(self._poll_interval)
            try:
                self._scan()
            except Exception as exc:
                logger.warning("PollingChangeDetector scan error: %s", exc)

    def _build_snapshot(self, initial: bool = False) -> dict[str, dict]:
        """
        Build a snapshot of all indexable files with mtime, size, sha256.

        Args:
            initial: If True, only scan without computing hashes (fast boot).

        Returns:
            {rel_path: {mtime, size, sha256}}
        """
        snapshot: dict[str, dict] = {}

        if not self.project_path.exists():
            return snapshot

        for root, dirs, files in os.walk(self.project_path):
            # Filter ignored directories
            dirs[:] = [d for d in dirs if not self._ignore.is_dir_ignored(d)]

            for fname in files:
                abs_path = str(Path(root) / fname)

                # Check ignore patterns
                rel = str(Path(abs_path).relative_to(self.project_path))
                if self._ignore.is_ignored(rel):
                    continue

                # Quick stat
                stat_result = HashCalculator.compute_stat(abs_path)
                if stat_result is None:
                    continue

                mtime, size = stat_result
                snapshot[rel] = {
                    "mtime": mtime,
                    "size": size,
                    "sha256": "",  # Will be computed by _scan
                }

        return snapshot

    def _scan(self) -> None:
        """Scan project tree and detect changes."""
        current_snapshot = self._build_snapshot()
        old_snapshot = self._snapshot

        # ── Detect new and modified files ────────────────────────
        for path, current in current_snapshot.items():
            old = old_snapshot.get(path)

            if old is None:
                # New file — compute hash to confirm
                abs_path = str(self.project_path / path)
                file_hash = HashCalculator.compute(abs_path)
                if file_hash:
                    current["sha256"] = file_hash
                    self._cache.set(
                        path, mtime=current["mtime"], size=current["size"], sha256=file_hash
                    )
                    if self._callback and self._dedup.acquire(path):
                        try:
                            self._callback(abs_path, "created")
                        finally:
                            self._dedup.release(path)

            else:
                # Existing file — check if mtime or size changed
                if (
                    old.get("mtime", 0.0) != current["mtime"]
                    or old.get("size", 0) != current["size"]
                ):
                    # Fast pass detected a change — precise pass via SHA256
                    abs_path = str(self.project_path / path)
                    file_hash = HashCalculator.compute(abs_path)

                    if file_hash is None:
                        continue

                    if file_hash != old.get("sha256", ""):
                        # Content actually changed
                        current["sha256"] = file_hash
                        self._cache.set(
                            path, mtime=current["mtime"], size=current["size"], sha256=file_hash
                        )
                        if self._callback and self._dedup.acquire(path):
                            try:
                                self._callback(abs_path, "modified")
                            finally:
                                self._dedup.release(path)
                    else:
                        # mtime/size changed but content same (e.g. touch)
                        # Update cache with new mtime/size without triggering reindex
                        self._cache.set(
                            path, mtime=current["mtime"], size=current["size"], sha256=file_hash
                        )

        # ── Detect deleted files ─────────────────────────────────
        for path in list(old_snapshot.keys()):
            if path not in current_snapshot:
                if self._callback and self._dedup.acquire(path):
                    try:
                        abs_path = str(self.project_path / path)
                        self._callback(abs_path, "deleted")
                    finally:
                        self._dedup.release(path)
                self._cache.delete(path)

        # Update snapshot
        self._snapshot = current_snapshot
