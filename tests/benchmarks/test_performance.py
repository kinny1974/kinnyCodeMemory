"""Performance benchmarks for KinnyCode Memory System."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

# Skip if dependencies not available
pytest.importorskip("memory.mscore")
pytest.importorskip("memory.hash_cache")


class TestMScorePerformance:
    """Benchmarks for M_score calculations."""

    def test_decay_factor_performance(self):
        from memory.mscore import decay_factor

        start = time.perf_counter()
        for _ in range(10000):
            decay_factor(30.0, 15.0)
        elapsed = time.perf_counter() - start

        # Should complete 10k calculations in < 100ms
        assert elapsed < 0.1, f"10k decay_factor calls took {elapsed:.3f}s"

    def test_calculate_m_score_performance(self):
        from memory.mscore import calculate_m_score

        start = time.perf_counter()
        for _ in range(10000):
            calculate_m_score(0.8, 15.0, 5, 30.0, 0.5)
        elapsed = time.perf_counter() - start

        # Should complete 10k calculations in < 100ms
        assert elapsed < 0.1, f"10k calculate_m_score calls took {elapsed:.3f}s"

    def test_consolidate_scores_performance(self):
        from memory.mscore import MemoryRelevanceManager

        mgr = MemoryRelevanceManager()
        # Create 1000 memories
        for i in range(1000):
            mgr.record_access(f"mem_{i}")

        memories = [
            {"memory_id": f"mem_{i}", "similarity": 0.5 + (i % 50) / 100.0}
            for i in range(1000)
        ]

        start = time.perf_counter()
        result = mgr.consolidate_scores(memories)
        elapsed = time.perf_counter() - start

        # Should consolidate 1000 memories in < 500ms
        assert elapsed < 0.5, f"1000 memory consolidation took {elapsed:.3f}s"
        assert len(result) == 1000
        # Verify sorting
        scores = [r["m_score"] for r in result]
        assert scores == sorted(scores, reverse=True)


class TestHashCachePerformance:
    """Benchmarks for HashCache operations."""

    def test_set_performance(self, tmp_path):
        from memory.hash_cache import HashCache

        cache = HashCache(str(tmp_path / "bench_cache.json"))

        start = time.perf_counter()
        for i in range(1000):
            cache.set(f"file_{i}.py", mtime=float(i), size=i * 100, sha256=f"hash_{i}")
        elapsed = time.perf_counter() - start

        # Should set 1000 entries in < 100ms
        assert elapsed < 0.1, f"1000 cache.set calls took {elapsed:.3f}s"

    def test_get_performance(self, tmp_path):
        from memory.hash_cache import HashCache

        cache = HashCache(str(tmp_path / "bench_cache.json"))
        for i in range(1000):
            cache.set(f"file_{i}.py", mtime=float(i), size=i * 100, sha256=f"hash_{i}")

        start = time.perf_counter()
        for i in range(1000):
            cache.get(f"file_{i}.py")
        elapsed = time.perf_counter() - start

        # Should get 1000 entries in < 50ms
        assert elapsed < 0.05, f"1000 cache.get calls took {elapsed:.3f}s"

    def test_save_load_performance(self, tmp_path):
        from memory.hash_cache import HashCache

        cache_path = tmp_path / "bench_cache.json"
        cache = HashCache(str(cache_path))
        for i in range(1000):
            cache.set(f"file_{i}.py", mtime=float(i), size=i * 100, sha256=f"hash_{i}")

        start = time.perf_counter()
        cache.save()
        elapsed_save = time.perf_counter() - start

        cache2 = HashCache(str(cache_path))
        start = time.perf_counter()
        cache2.load()
        elapsed_load = time.perf_counter() - start

        # Should save/load 1000 entries in < 500ms each
        assert elapsed_save < 0.5, f"Save 1000 entries took {elapsed_save:.3f}s"
        assert elapsed_load < 0.5, f"Load 1000 entries took {elapsed_load:.3f}s"


class TestValidationPerformance:
    """Benchmarks for validation operations."""

    def test_validate_project_id_performance(self):
        from memory.validation import validate_project_id

        start = time.perf_counter()
        for _ in range(10000):
            validate_project_id("my-project_123")
        elapsed = time.perf_counter() - start

        # Should validate 10k IDs in < 50ms
        assert elapsed < 0.05, f"10k validate_project_id calls took {elapsed:.3f}s"

    def test_auto_detect_project_id_performance(self):
        from memory.validation import auto_detect_project_id

        start = time.perf_counter()
        for _ in range(1000):
            auto_detect_project_id()
        elapsed = time.perf_counter() - start

        # Should auto-detect 1k times in < 5s (involves filesystem operations)
        assert elapsed < 5.0, f"1k auto_detect_project_id calls took {elapsed:.3f}s"
