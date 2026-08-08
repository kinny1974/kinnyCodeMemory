"""
KinnyCode — Ignore Patterns

Loads and evaluates file/directory ignore patterns from
.kinnycode/ignore (gitignore-style). Falls back to hardcoded
lists if the file does not exist.

Supported patterns:
    - Exact paths: `node_modules`
    - Glob patterns: `*.pyc`, `**/__pycache__`
    - Directory-only: `dist/`
    - Comments: # This is a comment
    - Negation: !important.py
"""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Hardcoded ignored directories (merged with .kinnycode/ignore)
HARDCODED_IGNORED_DIRS = {
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

# Hardcoded ignored extensions (merged with .kinnycode/ignore)
HARDCODED_IGNORED_EXTENSIONS = {
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

IGNORE_RULES_FILENAME = ".kinnycode/ignore"


class IgnorePatterns:
    """
    Evaluates file/directory paths against ignore patterns.

    Patterns are loaded from:
    1. .kinnycode/ignore (project-level, highest priority)
    2. Hardcoded directories and extensions (fallback)

    Usage:
        ignore = IgnorePatterns(project_path)
        ignore.load()

        if ignore.is_ignored("node_modules/foo.js"):
            skip
        if ignore.is_dir_ignored("build"):
            skip directory traversal
        if ignore.is_extension_ignored(".pyc"):
            skip
    """

    def __init__(self, project_path: str = "") -> None:
        self._project_path = Path(project_path).resolve() if project_path else None
        self._patterns: list[tuple[str, bool]] = []  # [(pattern, negation)]
        self._loaded: bool = False
        self._custom_files: set[str] = set()  # Files from .kinnycode/ignore

    # ── Loading ──────────────────────────────────────────────────

    def load(self, project_path: str | None = None) -> bool:
        """
        Load ignore patterns from .kinnycode/ignore.

        Returns:
            True if patterns were loaded successfully.
        """
        if project_path:
            self._project_path = Path(project_path).resolve()

        if not self._project_path:
            self._loaded = True
            logger.debug("No project path set, using hardcoded ignore lists only")
            return True

        ignore_file = self._project_path / IGNORE_RULES_FILENAME

        if not ignore_file.exists():
            self._loaded = True
            logger.debug("No ignore file found at %s, using hardcoded lists", ignore_file)
            return True

        try:
            with open(ignore_file, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            logger.warning("Failed to read ignore file: %s", e)
            self._loaded = True
            return True

        self._patterns = []
        self._custom_files = set()

        for _line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Handle negation
            negation = False
            if line.startswith("!"):
                negation = True
                line = line[1:].strip()

            # Store pattern (with or without trailing slash for dirs)
            self._patterns.append((line, negation))
            self._custom_files.add(line)

        self._loaded = True
        logger.info(
            "Loaded %d ignore patterns from %s",
            len(self._patterns),
            ignore_file,
        )
        return True

    # ── Evaluation ───────────────────────────────────────────────

    def is_ignored(self, relative_path: str) -> bool:
        """
        Check if a relative file path is ignored.

        Checks:
        1. Hardcoded ignored directories (if path is under one)
        2. Hardcoded ignored extensions
        3. Custom patterns from .kinnycode/ignore (last match wins, gitignore-style)

        Args:
            relative_path: Path relative to project root (e.g., "src/main.py")

        Returns:
            True if the path should be ignored.
        """
        parts = relative_path.replace("\\", "/").split("/")

        # Check hardcoded ignored directories
        if any(part in HARDCODED_IGNORED_DIRS for part in parts):
            return True

        # Check hardcoded ignored extensions
        if parts[-1]:
            ext = Path(parts[-1]).suffix.lower()
            if ext in HARDCODED_IGNORED_EXTENSIONS:
                return True

        # Check custom patterns from .kinnycode/ignore — last match wins
        # (gitignore semantics: later patterns override earlier ones)
        result = False  # default: not ignored by custom patterns
        for pattern, negation in self._patterns:
            if self._matches(pattern, relative_path, parts):
                result = not negation  # negation=true means NOT ignored

        return result

    def is_dir_ignored(self, dir_name: str) -> bool:
        """
        Check if a directory name should be skipped during traversal.

        Args:
            dir_name: Directory name (not full path, e.g., "node_modules")

        Returns:
            True if the directory should be skipped.
        """
        # Hardcoded dirs
        if dir_name in HARDCODED_IGNORED_DIRS:
            return True

        # Custom patterns — check as exact match and glob
        for pattern, negation in self._patterns:
            pattern_clean = pattern.rstrip("/")
            if fnmatch.fnmatch(dir_name, pattern_clean) or dir_name == pattern_clean:
                return not negation

        return False

    def is_extension_ignored(self, extension: str) -> bool:
        """
        Check if a file extension should be ignored.

        Args:
            extension: File extension with dot (e.g., ".pyc")

        Returns:
            True if the extension should be ignored.
        """
        ext = extension.lower() if extension else ""
        if ext in HARDCODED_IGNORED_EXTENSIONS:
            return True

        # Check custom patterns for glob extensions (e.g., "*.pyc")
        for pattern, negation in self._patterns:
            if pattern.startswith("*") and fnmatch.fnmatch(ext, pattern):
                return not negation

        return False

    def _matches(self, pattern: str, path: str, parts: list[str]) -> bool:
        """
        Check if a pattern matches a path.

        Supports:
        - Exact match: "node_modules"
        - Glob: "*.pyc", "**/__pycache__"
        - Path-relative: "src/generated/*"
        - Trailing slash (dir only): "build/" — matches dirs and their children
        """
        # Check if pattern ends with /
        if pattern.endswith("/"):
            pattern_clean = pattern.rstrip("/")
            # Check each individual path component
            for part in parts:
                if fnmatch.fnmatch(part, pattern_clean):
                    return True
            # Also check cumulative sub-paths
            for i in range(len(parts)):
                sub_path = "/".join(parts[: i + 1])
                if fnmatch.fnmatch(sub_path, pattern_clean):
                    return True
            return False

        # ** pattern (match any path)
        if "**" in pattern:
            # Convert ** pattern to fnmatch-compatible
            normalized = pattern.replace("**/", "").replace("/**", "")
            if not normalized:
                return True
            # Check if any path component matches
            for part in parts:
                if fnmatch.fnmatch(part, normalized):
                    return True
            # Also check full path
            if fnmatch.fnmatch(path, pattern.replace("**", "*")):
                return True
            return False

        # Check if pattern is a directory name (no path separator)
        if "/" not in pattern and "\\" not in pattern:
            # Match against filename and any directory component
            filename = parts[-1] if parts else ""
            if fnmatch.fnmatch(filename, pattern):
                return True
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
            return False

        # Full path pattern
        return fnmatch.fnmatch(path, pattern)

    # ── Properties ───────────────────────────────────────────────

    @property
    def patterns(self) -> list[tuple[str, bool]]:
        return list(self._patterns)

    @property
    def custom_files(self) -> set[str]:
        return set(self._custom_files)

    @property
    def is_loaded(self) -> bool:
        return self._loaded
