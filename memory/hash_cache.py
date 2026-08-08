"""
KinnyCode — Hash Cache Manager (v2)

Manages persistent hash cache for file change detection.
Supports v1 → v2 migration, chunk-based hashing metadata,
and garbage collection of invalidated entries.

Cache format (v2):
    {
        "version": 2,
        "files": {
            "<relative_path>": {
                "mtime": 1234567890.0,
                "size": 12345,
                "sha256": "abc123...",
                "block_hashes": {
                    "0": "block_hash_0",
                    "65536": "block_hash_1"
                },
                "invalidated": false
            }
        }
    }

Cache format (v1 — legacy):
    {
        "<relative_path>": "sha256_hash"
        OR
        "<relative_path>": {"mtime": 123.0, "sha256": "abc123"}
    }
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 2
DEFAULT_GC_THRESHOLD = 100  # Remove invalid entries after 100 scans


class HashCache:
    """
    Versioned cache manager for file change detection.

    Usage:
        cache = HashCache(cache_path)
        cache.load()

        # Get entry
        entry = cache.get("src/main.py")
        if entry is None:
            # New file
            ...

        # Set entry
        cache.set("src/main.py", mtime=123.0, size=5000, sha256="abc123...")

        # Invalidate entry
        cache.invalidate("src/main.py")

        # Persist
        cache.save()
        cache.save_and_gc()  # Save + remove invalidated entries
    """

    def __init__(self, cache_path: str) -> None:
        self._cache_path = Path(cache_path).resolve()
        self._version: int = 0
        self._files: dict[str, dict[str, Any]] = {}
        self._gc_count: int = 0
        self._loaded: bool = False

    # ── Load / Save ──────────────────────────────────────────────

    def load(self) -> bool:
        """
        Load cache from disk. Migrates v1 → v2 if needed.

        Returns:
            True if loaded successfully.
        """
        if self._cache_path.exists():
            try:
                with open(self._cache_path, encoding="utf-8") as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Corrupt cache file %s, starting fresh: %s", self._cache_path, e)
                raw = {}

            self._migrate(raw)
            self._loaded = True
            logger.info("Cache loaded: %d entries (v%d)", len(self._files), self._version)
            return True
        else:
            self._version = CACHE_SCHEMA_VERSION
            self._loaded = True
            logger.info("No cache file found, starting fresh (v%d)", CACHE_SCHEMA_VERSION)
            return True

    def save(self) -> bool:
        """
        Persist cache to disk.

        Returns:
            True if saved successfully.
        """
        if not self._loaded:
            logger.error("Cannot save: cache not loaded")
            return False

        try:
            parent = self._cache_path.parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": self._version,
                "files": self._files,
            }

            tmp_path = str(self._cache_path) + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)

            # Atomic rename (works on same filesystem)
            os.replace(tmp_path, str(self._cache_path))
            logger.debug("Cache saved: %d entries", len(self._files))
            return True
        except OSError as e:
            logger.error("Failed to save cache: %s", e)
            # Clean up tmp if it exists
            try:
                if Path(tmp_path).exists():
                    os.remove(tmp_path)
            except OSError:
                pass
            return False

    def save_and_gc(self) -> bool:
        """
        Save cache and garbage-collect invalidated entries.

        After GC_THRESHOLD scans with invalid entries, removes them.
        """
        self._gc_count += 1

        invalid_count = sum(1 for v in self._files.values() if v.get("invalidated", False))
        if self._gc_count >= DEFAULT_GC_THRESHOLD and invalid_count > 0:
            self._files = {k: v for k, v in self._files.items() if not v.get("invalidated", False)}
            logger.info(
                "GC: removed %d invalidated entries (ran %d cycles)", invalid_count, self._gc_count
            )
            self._gc_count = 0

        return self.save()

    # ── Migration ────────────────────────────────────────────────

    def _migrate(self, raw: dict[str, Any]) -> None:
        """
        Normalize raw cache data to v2 format.

        Handles:
        - v1 string format: {path: "sha256_hash"}
        - v1 partial dict format: {path: {"mtime": ..., "sha256": ...}}
        - v2 full format with block_hashes, version, invalidated
        """
        if not raw:
            self._version = CACHE_SCHEMA_VERSION
            self._files = {}
            return

        # Check if it's already v2 format
        if isinstance(raw, dict) and "version" in raw and "files" in raw:
            # Already v2 structure
            self._version = raw.get("version", CACHE_SCHEMA_VERSION)
            self._files = raw.get("files", {})
            if self._version != CACHE_SCHEMA_VERSION:
                logger.info("Upgrading cache from v%d to v%d", self._version, CACHE_SCHEMA_VERSION)
                self._upgrade_to_current()
            return

        # Legacy v1 format: flat {path: value}
        self._version = CACHE_SCHEMA_VERSION
        migrated = {}

        for path, val in raw.items():
            if isinstance(val, str):
                # v1 string format: {path: "sha256"}
                migrated[path] = {
                    "mtime": 0.0,
                    "size": 0,
                    "sha256": val,
                    "block_hashes": {},
                    "invalidated": False,
                }
                logger.debug("Migrated v1 string entry: %s", path)
            elif isinstance(val, dict):
                # v1 partial dict or v2 format
                if "mtime" in val or "sha256" in val:
                    # v1 partial: normalize
                    migrated[path] = {
                        "mtime": val.get("mtime", 0.0),
                        "size": val.get("size", 0),
                        "sha256": val.get("sha256", ""),
                        "block_hashes": val.get("block_hashes", {}),
                        "invalidated": val.get("invalidated", False),
                    }
                    if "mtime" not in val:
                        logger.debug("Migrated v1 partial entry: %s (added missing mtime)", path)
                else:
                    # Already v2 format, copy as-is
                    migrated[path] = val
            else:
                # Unknown format, skip
                logger.warning(
                    "Skipping unrecognized cache entry: %s (type=%s)", path, type(val).__name__
                )

        self._files = migrated

    def _upgrade_to_current(self) -> None:
        """Add missing fields to existing v2 entries for schema compatibility."""
        self._version = CACHE_SCHEMA_VERSION
        for _path, entry in self._files.items():
            if "size" not in entry:
                entry["size"] = 0
            if "block_hashes" not in entry:
                entry["block_hashes"] = {}
            if "invalidated" not in entry:
                entry["invalidated"] = False

    # ── CRUD Operations ──────────────────────────────────────────

    def get(self, file_path: str) -> dict[str, Any] | None:
        """
        Get cache entry for a file.

        Returns:
            Dict with {mtime, size, sha256, block_hashes, invalidated} or None.
        """
        entry = self._files.get(file_path)
        if entry and entry.get("invalidated", False):
            return None
        return entry

    def set(
        self,
        file_path: str,
        mtime: float,
        size: int = 0,
        sha256: str = "",
        block_hashes: dict[str, str] | None = None,
    ) -> None:
        """
        Set or update a cache entry.

        Args:
            file_path: Relative path to the file.
            mtime: File modification timestamp (os.stat.st_mtime).
            size: File size in bytes.
            sha256: SHA256 hex digest of the file content.
            block_hashes: Optional {offset: hash} for chunk-based hashing.
        """
        self._files[file_path] = {
            "mtime": mtime,
            "size": size,
            "sha256": sha256,
            "block_hashes": block_hashes or {},
            "invalidated": False,
        }

    def delete(self, file_path: str) -> bool:
        """
        Permanently remove a cache entry.

        Returns:
            True if the entry existed and was removed.
        """
        if file_path in self._files:
            del self._files[file_path]
            return True
        return False

    def invalidate(self, file_path: str) -> None:
        """
        Mark an entry as invalidated (soft-delete).
        Removed during GC.
        """
        if file_path in self._files:
            self._files[file_path]["invalidated"] = True
            logger.debug("Invalidated cache entry: %s", file_path)

    def has(self, file_path: str) -> bool:
        """Check if a valid cache entry exists for a file."""
        entry = self._files.get(file_path)
        return entry is not None and not entry.get("invalidated", False)

    # ── Bulk Operations ──────────────────────────────────────────

    def get_all_paths(self) -> set[str]:
        """Return set of all valid file paths in cache."""
        return {path for path, entry in self._files.items() if not entry.get("invalidated", False)}

    def remove_stale(self, existing_paths: set[str]) -> int:
        """
        Remove entries for files that no longer exist.

        Returns:
            Number of entries removed.
        """
        stale = set(self._files.keys()) - existing_paths
        for path in stale:
            self.invalidate(path)
        logger.info("Marked %d stale entries for removal", len(stale))
        return len(stale)

    def clear(self) -> None:
        """Clear all entries from cache."""
        self._files.clear()
        logger.info("Cache cleared")

    # ── Properties ───────────────────────────────────────────────

    @property
    def count(self) -> int:
        """Number of valid (non-invalidated) entries."""
        return sum(1 for v in self._files.values() if not v.get("invalidated", False))

    @property
    def version(self) -> int:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def path(self) -> Path:
        return self._cache_path
