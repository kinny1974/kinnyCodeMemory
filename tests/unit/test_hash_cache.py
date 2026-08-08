"""Tests for memory.hash_cache module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory.hash_cache import CACHE_SCHEMA_VERSION, HashCache


class TestHashCache:
    """Tests for HashCache class."""

    def test_init(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        assert cache.count == 0
        assert cache._version == 0

    def test_load_nonexistent(self, tmp_path):
        cache = HashCache(str(tmp_path / "nonexistent.json"))
        result = cache.load()
        # Returns True even when file doesn't exist (starts fresh)
        assert result is True
        assert cache.count == 0

    def test_set_and_get(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        cache.set("src/main.py", mtime=1234567890.0, size=5000, sha256="abc123")
        entry = cache.get("src/main.py")
        assert entry is not None
        assert entry["mtime"] == 1234567890.0
        assert entry["size"] == 5000
        assert entry["sha256"] == "abc123"
        assert entry["invalidated"] is False

    def test_get_nonexistent(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        assert cache.get("nonexistent.py") is None

    def test_invalidate(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        cache.set("src/main.py", mtime=123.0, size=100, sha256="abc")
        cache.invalidate("src/main.py")
        # After invalidation, get returns None (invalidated entries are filtered out)
        assert cache.get("src/main.py") is None
        # Check via has()
        assert cache.has("src/main.py") is False

    def test_invalidate_nonexistent(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        # Should not raise
        cache.invalidate("nonexistent.py")

    def test_is_valid(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        cache.set("src/main.py", mtime=123.0, size=100, sha256="abc")
        assert cache.has("src/main.py") is True
        cache.invalidate("src/main.py")
        assert cache.has("src/main.py") is False

    def test_save_and_load(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cache1 = HashCache(str(cache_path))
        cache1.load()  # Must load first
        cache1.set("src/main.py", mtime=123.0, size=100, sha256="abc123")
        cache1.set("src/utils.py", mtime=456.0, size=200, sha256="def456")
        cache1.save()

        cache2 = HashCache(str(cache_path))
        cache2.load()
        assert cache2.count == 2
        assert cache2.get("src/main.py")["sha256"] == "abc123"
        assert cache2.get("src/utils.py")["sha256"] == "def456"

    def test_save_and_gc(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cache = HashCache(str(cache_path))
        cache.load()  # Must load first
        cache.set("valid.py", mtime=1.0, size=10, sha256="a")
        cache.set("invalid.py", mtime=2.0, size=20, sha256="b")
        cache.invalidate("invalid.py")

        cache.save_and_gc()

        cache2 = HashCache(str(cache_path))
        cache2.load()
        assert cache2.count == 1
        assert cache2.get("valid.py") is not None
        assert cache2.get("invalid.py") is None

    def test_valid_files(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        cache.set("a.py", mtime=1.0, size=10, sha256="a")
        cache.set("b.py", mtime=2.0, size=20, sha256="b")
        cache.set("c.py", mtime=3.0, size=30, sha256="c")
        cache.invalidate("b.py")

        valid = cache.get_all_paths()
        assert valid == {"a.py", "c.py"}

    def test_migrate_v1_string_hash(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        # Write v1 format (string hash)
        cache_path.write_text(json.dumps({
            "src/main.py": "abc123def456"
        }))

        cache = HashCache(str(cache_path))
        cache.load()

        assert cache._version == CACHE_SCHEMA_VERSION
        assert cache.count == 1
        entry = cache.get("src/main.py")
        assert entry["sha256"] == "abc123def456"

    def test_migrate_v1_dict_hash(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        # Write v1 format (dict with mtime and sha256)
        cache_path.write_text(json.dumps({
            "src/main.py": {"mtime": 123.0, "sha256": "abc123"}
        }))

        cache = HashCache(str(cache_path))
        cache.load()

        assert cache._version == CACHE_SCHEMA_VERSION
        entry = cache.get("src/main.py")
        assert entry["mtime"] == 123.0
        assert entry["sha256"] == "abc123"

    def test_corrupt_cache_file(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cache_path.write_text("not valid json {{{")

        cache = HashCache(str(cache_path))
        cache.load()
        # Should start fresh
        assert cache.count == 0

    def test_count(self, tmp_path):
        cache = HashCache(str(tmp_path / "cache.json"))
        assert cache.count == 0
        cache.set("a.py", mtime=1.0, size=10, sha256="a")
        assert cache.count == 1
        cache.set("b.py", mtime=2.0, size=20, sha256="b")
        assert cache.count == 2
