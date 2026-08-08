"""
Validation — Input validation utilities.

This module provides validation functions for project_id and other inputs.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Regex pattern for valid project_id
# Allows alphanumeric, hyphens, and underscores, 1-64 characters
PROJECT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def validate_project_id(project_id: str | None) -> str:
    """Validate and normalize project_id.
    
    Args:
        project_id: Project ID to validate. Can be None for auto-detection.
        
    Returns:
        Validated project ID string.
        
    Raises:
        ValueError: If project_id format is invalid.
    """
    if project_id is None or project_id == "":
        return auto_detect_project_id()
    
    if not PROJECT_ID_PATTERN.match(project_id):
        raise ValueError(
            f"Invalid project_id format: '{project_id}'. "
            "Must be 1-64 characters, alphanumeric, hyphens, or underscores."
        )
    
    return project_id


def auto_detect_project_id() -> str:
    """Auto-detect project_id from environment or current directory.
    
    Resolution order:
        1. KINNYCODE_PROJECT_ID environment variable
        2. .kinnycode/memory.json in current directory tree
        3. SHA-256 hash of current working directory
        
    Returns:
        Detected project ID string.
    """
    import os
    
    # 1. Check environment variable
    env_id = os.environ.get("KINNYCODE_PROJECT_ID", "")
    if env_id:
        return env_id
    
    # 2. Walk up from CWD looking for .kinnycode/memory.json
    current = Path.cwd().resolve()
    for _ in range(10):
        config_file = current / ".kinnycode" / "memory.json"
        if config_file.is_file():
            try:
                import json
                data = json.loads(config_file.read_text(encoding="utf-8"))
                pid = data.get("project_id", "")
                if pid:
                    return pid
            except Exception:
                pass
        parent = current.parent
        if parent == current:
            break
        current = parent
    
    # 3. Fallback: derive from CWD hash
    cwd = str(Path.cwd().resolve())
    return hashlib.sha256(cwd.encode()).hexdigest()[:16]


def is_valid_project_id(project_id: str) -> bool:
    """Check if a project_id is valid without raising exceptions.
    
    Args:
        project_id: Project ID to validate.
        
    Returns:
        True if valid, False otherwise.
    """
    if not project_id:
        return True  # Empty is valid (will be auto-detected)
    return bool(PROJECT_ID_PATTERN.match(project_id))
