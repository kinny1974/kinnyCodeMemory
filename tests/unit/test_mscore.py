"""Tests for memory.mscore module — M_score Ebbinghaus decay."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pytest

from memory.mscore import (
    MemoryRelevanceManager,
    calculate_m_score,
    decay_factor,
)


class TestDecayFactor:
    """Tests for decay_factor pure function."""

    def test_zero_days(self):
        assert decay_factor(30.0, 0.0) == pytest.approx(1.0)

    def test_one_lambda_period(self):
        # At t = lambda_days, decay = e^(-1) ≈ 0.367879
        assert decay_factor(30.0, 30.0) == pytest.approx(math.exp(-1), abs=1e-6)

    def test_two_lambda_periods(self):
        # At t = 2 * lambda_days, decay = e^(-2) ≈ 0.135335
        assert decay_factor(30.0, 60.0) == pytest.approx(math.exp(-2), abs=1e-6)

    def test_half_lambda_period(self):
        # At t = lambda_days/2, decay = e^(-0.5) ≈ 0.606531
        assert decay_factor(30.0, 15.0) == pytest.approx(math.exp(-0.5), abs=1e-6)

    def test_custom_lambda(self):
        assert decay_factor(60.0, 60.0) == pytest.approx(math.exp(-1), abs=1e-6)

    def test_invalid_lambda_zero(self):
        with pytest.raises(ValueError, match="lambda_days must be positive"):
            decay_factor(0.0, 10.0)

    def test_invalid_lambda_negative(self):
        with pytest.raises(ValueError, match="lambda_days must be positive"):
            decay_factor(-1.0, 10.0)

    def test_invalid_t_days_negative(self):
        with pytest.raises(ValueError, match="t_days must be non-negative"):
            decay_factor(30.0, -1.0)


class TestCalculateMScore:
    """Tests for calculate_m_score function."""

    def test_perfect_similarity_no_decay(self):
        # similarity=1.0, days=0, freq=0 → score = 1.0
        assert calculate_m_score(1.0, 0.0, 0) == pytest.approx(1.0)

    def test_zero_similarity(self):
        assert calculate_m_score(0.0, 0.0, 0) == pytest.approx(0.0)

    def test_with_frequency(self):
        # similarity=0.8, days=0, freq=2, w_freq=0.5 → 0.8 + 0.5*2 = 1.8
        score = calculate_m_score(0.8, 0.0, 2, w_freq=0.5)
        assert score == pytest.approx(1.8)

    def test_with_decay(self):
        # similarity=1.0, days=30, freq=0, lambda=30 → 1.0 * e^(-1)
        score = calculate_m_score(1.0, 30.0, 0, lambda_days=30.0)
        assert score == pytest.approx(math.exp(-1), abs=1e-6)

    def test_combined_decay_and_frequency(self):
        # similarity=0.9, days=30, freq=1, lambda=30, w_freq=0.5
        # = 0.9 * e^(-1) + 0.5 * 1
        expected = 0.9 * math.exp(-1) + 0.5
        score = calculate_m_score(0.9, 30.0, 1, lambda_days=30.0, w_freq=0.5)
        assert score == pytest.approx(expected, abs=1e-6)

    def test_invalid_similarity_negative(self):
        with pytest.raises(ValueError, match="similarity must be between"):
            calculate_m_score(-0.1, 0.0)

    def test_invalid_similarity_above_one(self):
        with pytest.raises(ValueError, match="similarity must be between"):
            calculate_m_score(1.1, 0.0)

    def test_invalid_days_negative(self):
        with pytest.raises(ValueError, match="days_since_access must be non-negative"):
            calculate_m_score(0.5, -1.0)

    def test_invalid_frequency_negative(self):
        with pytest.raises(ValueError, match="access_frequency must be non-negative"):
            calculate_m_score(0.5, 0.0, -1)

    def test_invalid_w_freq_negative(self):
        with pytest.raises(ValueError, match="w_freq must be non-negative"):
            calculate_m_score(0.5, 0.0, 0, w_freq=-0.1)


class TestMemoryRelevanceManager:
    """Tests for MemoryRelevanceManager class."""

    def test_init_defaults(self):
        mgr = MemoryRelevanceManager()
        assert mgr.lambda_days == 30.0
        assert mgr.w_freq == 0.5
        assert mgr.count == 0

    def test_init_custom(self):
        mgr = MemoryRelevanceManager(lambda_days=60.0, w_freq=0.3)
        assert mgr.lambda_days == 60.0
        assert mgr.w_freq == 0.3

    def test_record_access(self):
        mgr = MemoryRelevanceManager()
        mgr.record_access("mem_1")
        assert mgr.get_access_count("mem_1") == 1
        assert "mem_1" in mgr.memory_ids

    def test_record_multiple_accesses(self):
        mgr = MemoryRelevanceManager()
        mgr.record_access("mem_1")
        mgr.record_access("mem_1")
        mgr.record_access("mem_1")
        assert mgr.get_access_count("mem_1") == 3

    def test_get_recent_access(self):
        mgr = MemoryRelevanceManager()
        mgr.record_access("mem_1")
        days = mgr.get_recent_access("mem_1")
        # Should be very close to 0
        assert 0.0 <= days < 0.001

    def test_get_recent_access_unknown(self):
        mgr = MemoryRelevanceManager()
        assert mgr.get_recent_access("unknown") == 0.0

    def test_get_access_count_unknown(self):
        mgr = MemoryRelevanceManager()
        assert mgr.get_access_count("unknown") == 0

    def test_get_score(self):
        mgr = MemoryRelevanceManager()
        mgr.record_access("mem_1")
        score = mgr.get_score("mem_1", similarity=0.8)
        # similarity=0.8, days≈0, freq=1
        # = 0.8 * 1.0 + 0.5 * 1 = 1.3
        assert score == pytest.approx(1.3, abs=0.01)

    def test_consolidate_scores(self):
        mgr = MemoryRelevanceManager()
        mgr.record_access("mem_1")
        mgr.record_access("mem_2")
        mgr.record_access("mem_2")

        memories = [
            {"memory_id": "mem_1", "similarity": 0.9, "data": "a"},
            {"memory_id": "mem_2", "similarity": 0.7, "data": "b"},
        ]
        result = mgr.consolidate_scores(memories)

        assert len(result) == 2
        # mem_1: 0.9 + 0.5 = 1.4
        # mem_2: 0.7 + 0.5*2 = 1.7
        # So mem_2 should be first
        assert result[0]["memory_id"] == "mem_2"
        assert result[1]["memory_id"] == "mem_1"
        assert "m_score" in result[0]

    def test_persist_and_load_state(self, tmp_path):
        mgr1 = MemoryRelevanceManager(lambda_days=45.0, w_freq=0.3)
        mgr1.record_access("mem_1")
        mgr1.record_access("mem_2")

        state_file = tmp_path / "mscore_state.json"
        mgr1.persist_state(str(state_file))

        mgr2 = MemoryRelevanceManager()
        mgr2.load_state(str(state_file))

        assert mgr2.lambda_days == 45.0
        assert mgr2.w_freq == 0.3
        assert mgr2.count == 2
        assert mgr2.get_access_count("mem_1") == 1
        assert mgr2.get_access_count("mem_2") == 1

    def test_load_state_nonexistent(self, tmp_path):
        mgr = MemoryRelevanceManager()
        mgr.load_state(str(tmp_path / "nonexistent.json"))
        # Should remain unchanged
        assert mgr.count == 0

    def test_clear(self):
        mgr = MemoryRelevanceManager()
        mgr.record_access("mem_1")
        mgr.record_access("mem_2")
        mgr.clear()
        assert mgr.count == 0
        assert len(mgr.memory_ids) == 0

    def test_persistence_json_format(self, tmp_path):
        mgr = MemoryRelevanceManager(lambda_days=30.0, w_freq=0.5)
        mgr.record_access("test_mem")

        state_file = tmp_path / "state.json"
        mgr.persist_state(str(state_file))

        data = json.loads(state_file.read_text())
        assert "lambda_days" in data
        assert "w_freq" in data
        assert "registry" in data
        assert "test_mem" in data["registry"]
