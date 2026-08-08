"""Tests for memory.validation module."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from memory.validation import (
    auto_detect_project_id,
    is_valid_project_id,
    validate_project_id,
)


class TestValidateProjectId:
    """Tests for validate_project_id function."""

    def test_valid_alphanumeric(self):
        assert validate_project_id("myproject") == "myproject"

    def test_valid_with_hyphens(self):
        assert validate_project_id("my-project") == "my-project"

    def test_valid_with_underscores(self):
        assert validate_project_id("my_project") == "my_project"

    def test_valid_mixed(self):
        assert validate_project_id("my-project_123") == "my-project_123"

    def test_valid_single_char(self):
        assert validate_project_id("a") == "a"

    def test_valid_max_length(self):
        pid = "a" * 64
        assert validate_project_id(pid) == pid

    def test_invalid_too_long(self):
        with pytest.raises(ValueError, match="Invalid project_id format"):
            validate_project_id("a" * 65)

    def test_invalid_special_chars(self):
        with pytest.raises(ValueError, match="Invalid project_id format"):
            validate_project_id("my project")

    def test_invalid_dots(self):
        with pytest.raises(ValueError, match="Invalid project_id format"):
            validate_project_id("my.project")

    def test_invalid_slash(self):
        with pytest.raises(ValueError, match="Invalid project_id format"):
            validate_project_id("my/project")

    def test_invalid_empty_string(self):
        # Empty string should trigger auto-detect
        result = validate_project_id("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_triggers_auto_detect(self):
        result = validate_project_id(None)
        assert isinstance(result, str)
        assert len(result) > 0


class TestIsValidProjectId:
    """Tests for is_valid_project_id function."""

    def test_valid_ids(self):
        assert is_valid_project_id("myproject") is True
        assert is_valid_project_id("my-project_123") is True
        assert is_valid_project_id("a") is True

    def test_invalid_ids(self):
        assert is_valid_project_id("my project") is False
        assert is_valid_project_id("my.project") is False
        assert is_valid_project_id("a" * 65) is False

    def test_empty_is_valid(self):
        assert is_valid_project_id("") is True
        assert is_valid_project_id(None) is True


class TestAutoDetectProjectId:
    """Tests for auto_detect_project_id function."""

    def test_from_env_variable(self):
        with patch.dict(os.environ, {"KINNYCODE_PROJECT_ID": "test-project"}):
            assert auto_detect_project_id() == "test-project"

    def test_fallback_to_cwd_hash(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove KINNYCODE_PROJECT_ID if set
            os.environ.pop("KINNYCODE_PROJECT_ID", None)
            result = auto_detect_project_id()
            # Should be a 16-char hex string
            assert len(result) == 16
            assert all(c in "0123456789abcdef" for c in result)

    def test_from_kinnycode_config(self, tmp_path):
        config_dir = tmp_path / ".kinnycode"
        config_dir.mkdir()
        config_file = config_dir / "memory.json"
        config_file.write_text('{"project_id": "config-project"}')

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("KINNYCODE_PROJECT_ID", None)
            with patch("memory.validation.Path.cwd", return_value=tmp_path):
                result = auto_detect_project_id()
                assert result == "config-project"
