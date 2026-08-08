"""
KinnyCode — Memory / RAG Client

Connects to the FastAPI memory_server.py on the configured port.
Supports multi-layer memory: codebase, architecture decisions,
conversation history, and semantic search.
"""

import os
from pathlib import Path

import requests

_SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".py": "python", ".pyi": "python", ".pyx": "python",
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".rs": "rust", ".go": "go",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".java": "java", ".kt": "kotlin",
    ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".sh": "bash", ".bash": "bash", ".ps1": "powershell",
    ".sql": "sql", ".html": "html", ".css": "css",
    ".md": "markdown", ".rst": "rst",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".json": "json", ".xml": "xml",
    ".vue": "vue", ".svelte": "svelte",
    ".dockerfile": "dockerfile", ".lua": "lua",
    ".r": "r", ".graphql": "graphql", ".proto": "protobuf",
}


def _get_memory_server_url() -> str:
    return os.environ.get("MEMORY_SERVER_URL", "http://127.0.0.1:8006")


class MemoryClient:
    """Thin client for the ChromaDB-backed multi-layer memory server."""

    def __init__(self, server_url: str | None = None):
        if server_url is not None:
            self.server_url = server_url.rstrip("/")
        else:
            self.server_url = _get_memory_server_url().rstrip("/")
        # Defer connection check — do NOT block the constructor.
        # Call reconnect() or check the `connected` property later.
        self.connected = False

    # ── Health ────────────────────────────────────────────────────
    def _check_connection(self) -> bool:
        try:
            r = requests.get(f"{self.server_url}/docs", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def reconnect(self) -> bool:
        self.connected = self._check_connection()
        return self.connected

    # ── RAG Query ─────────────────────────────────────────────────
    def query_context(self, prompt: str, n_results: int = 4) -> str:
        """Retrieve relevant context from all memory layers."""
        try:
            r = requests.post(
                f"{self.server_url}/retrieve-context",
                json={"prompt": prompt, "n_results": n_results},
                timeout=30,
            )
            if r.status_code == 200:
                return r.json().get("context", "")
        except Exception:
            pass
        return ""

    # ── Semantic Search ───────────────────────────────────────────
    def semantic_search(self, query: str, n_results: int = 10) -> list[dict]:
        """
        Perform semantic search across the indexed codebase.

        Returns:
            List of {"file_path": ..., "language": ..., "snippet": ..., "score": ...}
        """
        try:
            r = requests.post(
                f"{self.server_url}/semantic-search",
                json={"prompt": query, "n_results": n_results},
                timeout=15,
            )
            if r.status_code == 200:
                return r.json().get("results", [])
        except Exception:
            pass
        return []

    # ── Index a File ──────────────────────────────────────────────
    def index_file(self, file_path: str, content: str, language: str) -> bool:
        import hashlib

        try:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            r = requests.post(
                f"{self.server_url}/index-file",
                json={
                    "file_path": file_path,
                    "content": content,
                    "language": language,
                    "content_hash": content_hash,
                },
                timeout=60,
            )
            return r.status_code == 200
        except Exception:
            return False

    def reindex_file(self, file_path: str, content: str, language: str) -> bool:
        """Re-index a single file (clears previous chunks first)."""
        import hashlib

        try:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            r = requests.post(
                f"{self.server_url}/reindex-file",
                json={
                    "file_path": file_path,
                    "content": content,
                    "language": language,
                    "content_hash": content_hash,
                },
                timeout=60,
            )
            return r.status_code == 200
        except Exception:
            return False

    def index_file_by_path(self, file_path: str) -> bool:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            ext = Path(file_path).suffix.lower()
            lang = _SUPPORTED_EXTENSIONS.get(ext, "text")
            return self.index_file(file_path, content, lang)
        except Exception:
            return False

    def index_project_batch(self, files: list[dict], clear_first: bool = False) -> bool:
        """
        Batch-index multiple files.

        Args:
            files: [{"file_path":"...", "content":"...", "language":"..."}, ...]
            clear_first: If True, clear codebase collection first.
        """
        try:
            r = requests.post(
                f"{self.server_url}/index-project",
                json={"files": files, "clear_first": clear_first},
                timeout=300,
            )
            return r.status_code == 200
        except Exception:
            return False

    # ── Remember a Decision ───────────────────────────────────────
    def remember_decision(self, decision: str, context: str = "") -> bool:
        try:
            r = requests.post(
                f"{self.server_url}/remember-decision",
                json={"key_decision": decision, "context": context},
                timeout=30,
            )
            return r.status_code == 200
        except Exception:
            return False

    # ── Conversation ──────────────────────────────────────────────
    def save_conversation(
        self, session_id: str, messages: list[dict], summarise: bool = False
    ) -> bool:
        try:
            r = requests.post(
                f"{self.server_url}/save-conversation",
                json={"session_id": session_id, "messages": messages, "summarise": summarise},
                timeout=15,
            )
            return r.status_code == 200
        except Exception:
            return False

    def load_conversation(self, session_id: str, limit: int = 20) -> list[dict]:
        try:
            r = requests.post(
                f"{self.server_url}/load-conversation",
                json={"session_id": session_id, "limit": limit},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("messages", [])
        except Exception:
            pass
        return []

    def load_conversation_summary(self, session_id: str) -> str:
        try:
            r = requests.post(
                f"{self.server_url}/load-conversation",
                json={"session_id": session_id, "summary_only": True},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("summary", "")
        except Exception:
            pass
        return ""
