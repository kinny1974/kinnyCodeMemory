"""
KinnyCode — Conversation Store

Persists agent conversation history to the memory server and
retrieves it across sessions. Supports periodic summarization
to keep context manageable.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import requests


class ConversationStore:
    """
    Manages conversation persistence via the memory server.

    Stores conversation turns so the agent can "remember" what was
    discussed in previous sessions.
    """

    def __init__(self, server_url: str = "http://127.0.0.1:8006"):
        self.server_url = server_url.rstrip("/")
        self._session_id: str | None = None

    # ── Session management ─────────────────────────────────────────
    def start_session(self, project_path: str = "") -> str:
        """Create a new conversation session. Returns session_id."""
        clean_path = project_path.replace("/", "_").replace("\\", "_")
        self._session_id = f"conv_{clean_path}_{int(time.time())}"
        return self._session_id

    def get_session_id(self) -> str | None:
        return self._session_id

    # ── Save / Load ────────────────────────────────────────────────
    def save_conversation(self, messages: list[dict], summarise: bool = False) -> bool:
        """
        Persist the conversation history to the memory server.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            summarise: If True, request the server to summarise old turns.

        Returns:
            True on success.
        """
        if not self._session_id:
            return False

        try:
            r = requests.post(
                f"{self.server_url}/save-conversation",
                json={
                    "session_id": self._session_id,
                    "messages": messages,
                    "summarise": summarise,
                },
                timeout=15,
            )
            return r.status_code == 200
        except Exception:
            return False

    def load_conversation(self, limit: int = 20) -> list[dict]:
        """
        Load recent conversation turns from the memory server.

        Args:
            limit: Maximum number of recent turns to retrieve.

        Returns:
            List of message dicts.
        """
        if not self._session_id:
            return []

        try:
            r = requests.post(
                f"{self.server_url}/load-conversation",
                json={"session_id": self._session_id, "limit": limit},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("messages", [])
        except Exception:
            pass
        return []

    def load_summary(self) -> str:
        """
        Load the summarised context from the most recent conversation.

        Returns:
            Summary string, or empty string if unavailable.
        """
        if not self._session_id:
            return ""

        try:
            r = requests.post(
                f"{self.server_url}/load-conversation",
                json={"session_id": self._session_id, "summary_only": True},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("summary", "")
        except Exception:
            pass
        return ""
