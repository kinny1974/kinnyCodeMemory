"""
KinnyCode — Project Rules Loader

Loads project-specific rules from .kinnycode/rules.md.
These rules are injected into the agent's system prompt so it
always respects project conventions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class ProjectRules:
    """
    Loads and caches project rules from .kinnycode/rules.md.

    Rules can include:
    - Coding conventions (naming, style)
    - Architecture constraints
    - Testing requirements
    - Tech stack guidelines
    """

    DEFAULT_FILENAME = ".kinnycode/rules.md"

    def __init__(self, project_path: str = ""):
        self._project_path = project_path
        self._rules_text: str = ""
        self._loaded = False

    def load(self, project_path: str | None = None) -> str:
        """
        Load rules from the project directory.

        Returns:
            The rules text (may be empty if no file exists).
        """
        if project_path:
            self._project_path = project_path

        if not self._project_path:
            self._loaded = True
            return ""

        rules_file = Path(self._project_path) / self.DEFAULT_FILENAME
        if not rules_file.exists():
            self._loaded = True
            return ""

        try:
            with open(rules_file, encoding="utf-8") as f:
                self._rules_text = f.read().strip()
        except Exception:
            self._rules_text = ""

        self._loaded = True
        return self._rules_text

    @property
    def rules_text(self) -> str:
        if not self._loaded:
            self.load()
        return self._rules_text

    @property
    def has_rules(self) -> bool:
        return bool(self.rules_text)

    def to_system_prompt(self) -> str:
        """Format rules as a system prompt section."""
        if not self.has_rules:
            return ""
        return (
            "## Project Rules (from .kinnycode/rules.md)\n"
            "You MUST follow these rules at all times:\n\n"
            f"{self.rules_text}\n"
        )


def load_project_rules(project_path: str) -> ProjectRules:
    """Convenience function to load rules for a project."""
    rules = ProjectRules(project_path)
    rules.load()
    return rules
