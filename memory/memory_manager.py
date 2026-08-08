"""
KinnyCode — Memory Manager (Sprint 4)

Unified orchestrator for multi-layer memory system:

    L1: WorkingMemory  (RAM, TTL 15 min)          → in-memory session store
    L2: EpisodicMemory  (SQLite WAL, chats/events) → ConversationStore
    L3: SemanticMemory  (LanceDB, embeddings, RAG) → MemoryClient
    L4: ProceduralMemory (reglas, convenciones)    → ProjectRules

Features:
- Semantic search across indexed codebase (L3)
- Conversation persistence and recovery (L2)
- Project rules injection (L4)
- File indexing via change detection (L3 + L1)
- Memory consolidation with M_score (mscore)

Usage:
    manager = MemoryManager(project_path="/path/to/project")
    manager.open_project()

    # Semantic search
    results = await manager.semantic_search("authentication logic")

    # Store a conversation turn
    await manager.store_turn("user", "Hello, help me refactor")

    # Get consolidated context for agent prompt
    context = await manager.get_agent_context(query="how does auth work?")

    # Open/close project
    manager.open_project("/new/path")
    manager.close_project()
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .change_detector import (
    DedupLock,
    HashCalculator,
    PollingChangeDetector,
)
from .conversation_store import ConversationStore
from .hash_cache import HashCache
from .ignore_patterns import IgnorePatterns
from .mscore import MemoryRelevanceManager, calculate_m_score
from .project_rules import ProjectRules

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────

WORKING_MEMORY_TTL = 900  # 15 minutes in seconds
EPISODIC_DB_NAME = "episodic.db"
MSCORE_STATE_NAME = "mscore_state.json"
HASH_CACHE_NAME = "hash_cache.json"


# ── Data Classes ───────────────────────────────────────────────────────

@dataclass
class MemoryChunk:
    """Represents a single memory chunk from any layer."""

    memory_id: str
    content: str
    layer: str  # "l1", "l2", "l3", "l4"
    similarity: float = 0.0
    m_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationTurn:
    """A single turn in a conversation session."""

    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    turn_index: int = 0


# ── L1: Working Memory ────────────────────────────────────────────────

class WorkingMemory:
    """
    L1 — Short-term memory stored in RAM with TTL.

    Stores recent conversation turns, recent file reads,
    and transient state that should expire after a session.

    Usage:
        wm = WorkingMemory(ttl=900)
        wm.store("recent_file", "/path/to/main.py")
        value = wm.get("recent_file")
        wm.clear_expired()
    """

    def __init__(self, ttl: int = WORKING_MEMORY_TTL) -> None:
        """Initialize working memory.

        Args:
            ttl: Time-to-live in seconds (default 15 min).
        """
        self._ttl = ttl
        self._store: dict[str, dict[str, Any]] = {}

    def store(self, key: str, value: Any) -> None:
        """Store a value with the current timestamp.

        Args:
            key: Unique key for this memory item.
            value: The value to store (any serializable type).
        """
        self._store[key] = {
            "value": value,
            "created_at": time.time(),
            "last_accessed": time.time(),
        }

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key. Returns None if expired or missing.

        Args:
            key: The key to look up.

        Returns:
            The stored value, or None if not found/expired.
        """
        entry = self._store.get(key)
        if entry is None:
            return None

        # Check TTL
        if time.time() - entry["created_at"] > self._ttl:
            del self._store[key]
            return None

        # Update last accessed
        entry["last_accessed"] = time.time()
        return entry["value"]

    def has(self, key: str) -> bool:
        """Check if a key exists and is not expired.

        Args:
            key: The key to check.

        Returns:
            True if the key exists and is valid.
        """
        return self.get(key) is not None

    def delete(self, key: str) -> bool:
        """Remove a key from working memory.

        Args:
            key: The key to remove.

        Returns:
            True if the key existed and was removed.
        """
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed.
        """
        now = time.time()
        expired = [
            k for k, v in self._store.items()
            if now - v["created_at"] > self._ttl
        ]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def keys(self) -> set[str]:
        """Return set of valid (non-expired) keys."""
        now = time.time()
        return {
            k for k, v in self._store.items()
            if now - v["created_at"] <= self._ttl
        }

    @property
    def count(self) -> int:
        """Number of valid entries."""
        return len(self.keys)

    def clear(self) -> None:
        """Remove all entries."""
        self._store.clear()


# ── L2: Episodic Memory Manager ──────────────────────────────────────

class EpisodicMemoryManager:
    """
    L2 — Episodic memory using SQLite WAL mode.

    Stores conversation events, terminal logs, error traces,
    and agent actions. WAL mode allows concurrent reads.

    Tables:
        conversations: session_id, summary, turn_count, created_at
        turns: id, session_id, role, content, timestamp
        agent_actions: id, session_id, action_type, details, timestamp

    Usage:
        em = EpisodicMemoryManager(db_path)
        em.create_tables()
        em.start_session(project_path)
        em.add_turn(session_id, "user", "Hello")
        em.load_turns(session_id, limit=10)
    """

    def __init__(self, db_path: str) -> None:
        """Initialize episodic memory manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection with WAL mode."""
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def create_tables(self) -> None:
        """Create the required tables if they don't exist."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                session_id TEXT PRIMARY KEY,
                summary TEXT DEFAULT '',
                turn_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                turn_index INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES conversations(session_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_turns_session
                ON turns(session_id, turn_index);

            CREATE TABLE IF NOT EXISTS agent_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                details TEXT DEFAULT '',
                timestamp REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES conversations(session_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_actions_session
                ON agent_actions(session_id, timestamp);
        """)
        conn.commit()

    def start_session(self, project_path: str = "") -> str:
        """Create a new conversation session.

        Args:
            project_path: Optional project path for session ID generation.

        Returns:
            The session_id for the new session.
        """
        session_id = f"conv_{int(time.time())}_{hash(project_path) % 10000}"
        now = time.time()
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO conversations "
            "(session_id, summary, turn_count, created_at, updated_at) "
            "VALUES (?, '', 0, ?, ?)",
            (session_id, now, now),
        )
        conn.commit()
        logger.info("EpisodicMemory: started session %s", session_id)
        return session_id

    def add_turn(self, session_id: str, role: str, content: str) -> int:
        """Add a conversation turn to a session.

        Args:
            session_id: The session to add to.
            role: Message role (user, assistant, system, tool).
            content: Message content.

        Returns:
            The turn_index of the new turn.
        """
        conn = self._get_connection()

        # Get current turn count
        row = conn.execute(
            "SELECT turn_count FROM conversations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        turn_index = row[0] if row else 0

        now = time.time()
        conn.execute(
            "INSERT INTO turns (session_id, role, content, timestamp, turn_index) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, now, turn_index),
        )
        conn.execute(
            "UPDATE conversations SET turn_count = turn_count + 1, updated_at = ? "
            "WHERE session_id = ?",
            (now, session_id),
        )
        conn.commit()
        return turn_index

    def load_turns(self, session_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
        """Load conversation turns for a session.

        Args:
            session_id: The session to load from.
            limit: Maximum number of turns to return.
            offset: Number of turns to skip.

        Returns:
            List of {"role": ..., "content": ..., "timestamp": ...} dicts.
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT role, content, timestamp FROM turns "
            "WHERE session_id = ? ORDER BY turn_index ASC "
            "LIMIT ? OFFSET ?",
            (session_id, limit, offset),
        )
        return [
            {"role": row[0], "content": row[1], "timestamp": row[2]}
            for row in cursor.fetchall()
        ]

    def load_summary(self, session_id: str) -> str:
        """Load the summary for a session.

        Args:
            session_id: The session to load.

        Returns:
            Summary string, or empty string if none.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT summary FROM conversations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else ""

    def update_summary(self, session_id: str, summary: str) -> None:
        """Update the session summary.

        Args:
            session_id: The session to update.
            summary: New summary text.
        """
        conn = self._get_connection()
        now = time.time()
        conn.execute(
            "UPDATE conversations SET summary = ?, updated_at = ? "
            "WHERE session_id = ?",
            (summary, now, session_id),
        )
        conn.commit()

    def get_session_count(self) -> int:
        """Return the number of stored sessions."""
        conn = self._get_connection()
        row = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
        return row[0]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# ── L3: Semantic Memory Manager ──────────────────────────────────────

class SemanticMemoryManager:
    """
    L3 — Semantic memory using LanceDB (embedded).

    Stores file chunks as vectors for RAG-based retrieval.
    Supports incremental indexing and embedding configuration.

    Usage:
        sm = SemanticMemoryManager(lancedb_path)
        sm.create_collection("codebase")
        sm.add_chunks([{"id": "1", "text": "def foo(): ..."}])
        results = sm.search("function definition", top_k=5)
    """

    def __init__(
        self,
        lancedb_path: str,
        embedding_dim: int = 384,
    ) -> None:
        """Initialize semantic memory manager.

        Args:
            lancedb_path: Path to the LanceDB data directory.
            embedding_dim: Dimension of embeddings (default 384 for MiniLM).
        """
        self._lancedb_path = Path(lancedb_path)
        self._embedding_dim = embedding_dim
        self._db = None
        self._collection = None

    def connect(self) -> None:
        """Connect to LanceDB."""
        import lancedb as ldb

        self._lancedb_path.mkdir(parents=True, exist_ok=True)
        self._db = ldb.connect(str(self._lancedb_path))

    def create_collection(self, name: str = "codebase") -> None:
        """Create or open a LanceDB collection.

        Args:
            name: Collection name.
        """
        if self._db is None:
            self.connect()

        import lancedb as ldb

        if name not in self._db.list_tables():
            import pyarrow as pa

            schema = pa.schema([
                ("id", pa.string()),
                ("text", pa.string()),
                ("vector", pa.list_(pa.float32(), self._embedding_dim)),
                ("file_path", pa.string()),
                ("language", pa.string()),
                ("chunk_index", pa.int32()),
                ("content_hash", pa.string()),
            ])
            self._collection = self._db.create_table(
                name,
                schema=schema,
            )
        else:
            self._collection = self._db.open_table(name)

        logger.info("SemanticMemory: collection '%s' ready", name)

    def add_chunks(
        self,
        chunks: list[dict[str, Any]],
        embed_fn=None,
    ) -> int:
        """Add text chunks to the collection.

        Args:
            chunks: List of {"id", "text", "file_path", "language",
                     "chunk_index", "content_hash"} dicts.
            embed_fn: Optional callable(text) -> list[float] for embeddings.
                      If None, uses zero-vector placeholder.

        Returns:
            Number of chunks added.
        """
        if self._collection is None:
            self.create_collection()

        records = []
        for chunk in chunks:
            text = chunk["text"]
            if embed_fn is not None:
                vector = embed_fn(text)
            else:
                vector = [0.0] * self._embedding_dim

            records.append({
                "id": chunk["id"],
                "text": text,
                "vector": [float(v) for v in vector],
                "file_path": chunk.get("file_path", ""),
                "language": chunk.get("language", "text"),
                "chunk_index": chunk.get("chunk_index", 0),
                "content_hash": chunk.get("content_hash", ""),
            })

        if records:
            self._collection.add(records)
            logger.info("SemanticMemory: added %d chunks", len(records))
        return len(records)

    def search(
        self,
        query: str,
        top_k: int = 5,
        embed_fn=None,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks.

        Args:
            query: Search query string.
            top_k: Number of results to return.
            embed_fn: Optional embedding function.

        Returns:
            List of matching chunks with similarity scores.
        """
        if self._collection is None:
            self.create_collection()

        if embed_fn is not None:
            query_vector = embed_fn(query)
            results = (
                self._collection.search(query_vector).limit(top_k).to_list()
            )
        else:
            # Fallback: zero-vector search (returns limited results)
            zero_vec = [0.0] * self._embedding_dim
            results = (
                self._collection.search(zero_vec).limit(top_k).to_list()
            )

        output = []
        for row in results:
            output.append({
                "id": row.get("id", ""),
                "text": row.get("text", ""),
                "file_path": row.get("file_path", ""),
                "language": row.get("language", ""),
                "chunk_index": row.get("chunk_index", 0),
                "similarity": float(row.get("_distance", 0.0)),
            })
        return output

    def delete_by_hash(self, content_hash: str) -> int:
        """Delete all chunks with a given content hash.

        Args:
            content_hash: SHA256 hash of the file content.

        Returns:
            Number of chunks deleted.
        """
        if self._collection is None:
            self.create_collection()

        self._collection.delete(f"content_hash = '{content_hash}'")
        return 1  # Approximation since LanceDB doesn't return count

    def clear(self) -> None:
        """Remove all data from the collection."""
        if self._db is not None and self._collection is not None:
            self._collection.delete("1=1")

    def close(self) -> None:
        """Close the LanceDB connection."""
        if self._db is not None:
            del self._db
            self._db = None
            self._collection = None


# ── L4: Procedural Memory (Project Rules) ────────────────────────────

# Already implemented in project_rules.py
# ProceduralMemoryManager wraps ProjectRules for unified access

class ProceduralMemoryManager:
    """
    L4 — Procedural memory manager wrapping ProjectRules.

    Loads and caches project conventions, coding standards,
    and architecture rules. Provides system prompt formatting.
    """

    def __init__(self, project_path: str = "") -> None:
        """Initialize procedural memory.

        Args:
            project_path: Root path of the project.
        """
        self._project_path = project_path
        self._rules: ProjectRules | None = None

    def load(self, project_path: str | None = None) -> str:
        """Load project rules.

        Args:
            project_path: Optional override project path.

        Returns:
            The rules text, or empty string if none.
        """
        path = project_path or self._project_path
        self._rules = ProjectRules(path)
        return self._rules.load()

    @property
    def rules_text(self) -> str:
        """Get the current rules text."""
        if self._rules is None:
            return ""
        return self._rules.rules_text

    @property
    def has_rules(self) -> bool:
        """Check if rules exist."""
        if self._rules is None:
            return False
        return self._rules.has_rules

    def to_system_prompt(self) -> str:
        """Format rules as a system prompt section.

        Returns:
            Formatted rules string for agent system prompt.
        """
        if self._rules is None:
            return ""
        return self._rules.to_system_prompt()


# ── Main Memory Manager ──────────────────────────────────────────────

class MemoryManager:
    """
    Unified memory manager orchestrating L1-L4 layers.

    Manages:
        - WorkingMemory (L1): short-term RAM cache
        - EpisodicMemory (L2): SQLite conversation persistence
        - SemanticMemory (L3): LanceDB vector search
        - ProceduralMemory (L4): project rules and conventions

    Also integrates:
        - FileWatcher: automatic indexing on file changes
        - HashCache: change detection cache
        - MScoreManager: memory relevance scoring

    Usage:
        manager = MemoryManager(project_path="/path/to/project")
        manager.open_project()

        # Semantic search
        results = manager.semantic_search("authentication")

        # Store conversation
        manager.store_turn("user", "Hello")
        manager.store_turn("assistant", "Hi there!")

        # Get context for agent
        context = manager.get_agent_context("auth implementation")

        manager.close_project()
    """

    def __init__(
        self,
        project_path: str = "",
        base_data_dir: str | None = None,
    ) -> None:
        """Initialize MemoryManager.

        Args:
            project_path: Root path of the project to manage.
            base_data_dir: Base directory for memory data files.
                          Defaults to %APPDATA%/KinnyCode/memory/.
        """
        self._project_path = project_path
        self._base_data_dir = Path(
            base_data_dir or str(Path.home() / ".local" / "share" / "KinnyCode" / "memory")
        )

        # L1: Working memory
        self._working_memory = WorkingMemory(ttl=WORKING_MEMORY_TTL)

        # L2: Episodic memory (SQLite)
        self._episodic_db = self._base_data_dir / EPISODIC_DB_NAME
        self._episodic = EpisodicMemoryManager(str(self._episodic_db))

        # L3: Semantic memory (LanceDB)
        self._semantic_db = self._base_data_dir / "semantic"
        self._semantic = SemanticMemoryManager(str(self._semantic_db))

        # L4: Procedural memory (Project Rules)
        self._procedural = ProceduralMemoryManager(project_path)

        # Cross-cutting
        self._mscore = MemoryRelevanceManager()
        self._hash_cache_path = self._base_data_dir / HASH_CACHE_NAME
        self._hash_cache: HashCache | None = None
        self._ignore_patterns = IgnorePatterns()
        self._conversation_store = ConversationStore()
        self._detector: PollingChangeDetector | None = None
        self._watcher_running = False

    # ── Lifecycle ────────────────────────────────────────────────────

    def open_project(self, project_path: str | None = None) -> None:
        """Open a project and initialize all memory layers.

        Args:
            project_path: Optional new project path. Uses current if None.
        """
        if project_path:
            self._project_path = project_path

        if not self._project_path:
            logger.warning("MemoryManager: no project path set")
            return

        # Ensure base data directory exists
        self._base_data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize L2 (Episodic)
        self._episodic.create_tables()

        # Initialize L3 (Semantic)
        self._semantic.create_collection("codebase")

        # Load L4 (Procedural)
        self._procedural.load(self._project_path)

        # Load hash cache
        self._hash_cache = HashCache(str(self._hash_cache_path))
        self._hash_cache.load()

        # Load ignore patterns
        self._ignore_patterns.load(self._project_path)

        # Start change detector
        self._start_change_detector()

        logger.info(
            "MemoryManager: project opened — %s", self._project_path
        )

    def close_project(self) -> None:
        """Close the current project and clean up resources."""
        self._stop_change_detector()

        # Save hash cache
        if self._hash_cache:
            self._hash_cache.save()

        # Save mscore state
        mscore_path = self._base_data_dir / MSCORE_STATE_NAME
        self._mscore.persist_state(str(mscore_path))

        # Close L2 and L3
        self._episodic.close()
        self._semantic.close()

        logger.info("MemoryManager: project closed")

    # ── L1: Working Memory ──────────────────────────────────────────

    def working_store(self, key: str, value: Any) -> None:
        """Store a value in working memory (L1).

        Args:
            key: Unique key.
            value: Value to store.
        """
        self._working_memory.store(key, value)

    def working_get(self, key: str) -> Any | None:
        """Get a value from working memory.

        Args:
            key: The key to look up.

        Returns:
            The stored value or None.
        """
        return self._working_memory.get(key)

    # ── L2: Episodic Memory ─────────────────────────────────────────

    def start_conversation_session(self) -> str:
        """Start a new conversation session (L2).

        Returns:
            The session_id.
        """
        session_id = self._episodic.start_session(self._project_path)
        # Sync conversation store with the same session_id
        self._conversation_store._session_id = session_id
        return session_id

    def store_turn(self, role: str, content: str) -> None:
        """Store a conversation turn (L2).

        Args:
            role: Message role (user, assistant, system, tool).
            content: Message content.
        """
        session_id = self._conversation_store.get_session_id()
        if session_id:
            # Sync session IDs between episodic and conversation_store
            episodic_session = self._episodic._get_connection().execute(
                "SELECT session_id FROM conversations WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if episodic_session is None:
                episodic_id = self._episodic.start_session(self._project_path)
                self._conversation_store._session_id = episodic_id
                session_id = episodic_id
            try:
                turn_index = self._episodic.add_turn(session_id, role, content)
                self._mscore.record_access(f"turn_{session_id}_{turn_index}")
            except Exception:
                episodic_id = self._episodic.start_session(self._project_path)
                self._conversation_store._session_id = episodic_id
                self._episodic.add_turn(episodic_id, role, content)

    def load_turns(self, limit: int = 20) -> list[dict]:
        """Load recent conversation turns (L2).

        Args:
            limit: Maximum number of turns to return.

        Returns:
            List of turn dicts.
        """
        session_id = self._conversation_store.get_session_id()
        if not session_id:
            return []
        return self._episodic.load_turns(session_id, limit=limit)

    def get_conversation_summary(self) -> str:
        """Get the current session summary.

        Returns:
            Summary string.
        """
        session_id = self._conversation_store.get_session_id()
        if not session_id:
            return ""
        return self._episodic.load_summary(session_id)

    # ── L3: Semantic Memory ─────────────────────────────────────────

    def semantic_search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Perform semantic search across indexed codebase (L3).

        Args:
            query: Search query.
            top_k: Number of results.

        Returns:
            List of matching chunks with file_path, text, similarity.
        """
        results = self._semantic.search(query, top_k=top_k)

        # Apply M_score
        scored = []
        for r in results:
            mid = r.get("id", "")
            sim = max(0.0, 1.0 - r.get("similarity", 0.0))
            self._mscore.record_access(mid)
            m_score = self._mscore.get_score(mid, sim)
            scored.append({
                **r,
                "similarity": sim,
                "m_score": m_score,
            })

        return scored

    def index_file(self, file_path: str) -> bool:
        """Index a single file into semantic memory (L3).

        Performs incremental indexing: only re-indexes if content changed.

        Args:
            file_path: Absolute path to the file.

        Returns:
            True if the file was indexed.
        """
        if self._hash_cache is None:
            return False

        try:
            rel_path = str(Path(file_path).relative_to(self._project_path))
            cached = self._hash_cache.get(rel_path)

            # Check if file changed
            current_hash = HashCalculator.compute(file_path)
            if cached and cached.get("sha256") == current_hash:
                logger.debug("Indexing skipped (unchanged): %s", rel_path)
                return False

            # Read and chunk the file
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()

            ext = Path(file_path).suffix.lower()
            _lang_map = {
                ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript",
                ".ts": "typescript", ".tsx": "typescript", ".rs": "rust", ".go": "go",
                ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
                ".java": "java", ".kt": "kotlin", ".rb": "ruby", ".php": "php",
                ".sh": "bash", ".ps1": "powershell", ".sql": "sql",
                ".html": "html", ".css": "css", ".md": "markdown", ".rst": "rst",
                ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
                ".json": "json", ".xml": "xml", ".vue": "vue",
                ".dockerfile": "dockerfile", ".lua": "lua",
            }
            language = _lang_map.get(ext, "text")

            # Create chunks (simple line-based)
            chunks = self._chunk_text(content, file_path, language, current_hash)

            if chunks:
                self._semantic.add_chunks(chunks)

            # Update hash cache
            if current_hash:
                stat = HashCalculator.compute_stat(file_path)
                if stat:
                    self._hash_cache.set(
                        rel_path,
                        mtime=stat[0],
                        size=stat[1],
                        sha256=current_hash,
                    )

            logger.info("Indexed %d chunks for %s", len(chunks), rel_path)
            return True

        except Exception as e:
            logger.error("Failed to index %s: %s", file_path, e)
            return False

    def index_project(self) -> int:
        """Index all indexable files in the project (L3).

        Returns:
            Number of files indexed.
        """
        if not self._project_path:
            return 0

        count = 0
        for root, dirs, files in __import__("os").walk(self._project_path):
            dirs[:] = [d for d in dirs if not self._ignore_patterns.is_dir_ignored(d)]

            for fname in files:
                abs_path = str(Path(root) / fname)
                rel_path = str(Path(abs_path).relative_to(self._project_path))

                if self._ignore_patterns.is_ignored(rel_path):
                    continue

                if self.index_file(abs_path):
                    count += 1

        return count

    def reindex_file(self, file_path: str) -> bool:
        """Re-index a file (clear previous + re-index).

        Args:
            file_path: Absolute path to the file.

        Returns:
            True if re-indexed successfully.
        """
        try:
            content_hash = HashCalculator.compute(file_path)
            if content_hash:
                self._semantic.delete_by_hash(content_hash)
            return self.index_file(file_path)
        except Exception as e:
            logger.error("Failed to reindex %s: %s", file_path, e)
            return False

    # ── L4: Procedural Memory ───────────────────────────────────────

    def get_project_rules_prompt(self) -> str:
        """Get project rules formatted for agent system prompt (L4).

        Returns:
            Rules string for injection.
        """
        return self._procedural.to_system_prompt()

    # ── Cross-Layer Integration ─────────────────────────────────────

    def get_agent_context(self, query: str, top_k: int = 5) -> str:
        """Build a consolidated context string for the agent.

        Integrates L1 (working memory), L3 (semantic search),
        and L4 (project rules).

        Args:
            query: The agent's current query/context need.
            top_k: Number of semantic results.

        Returns:
            Formatted context string.
        """
        parts = []

        # L4: Project rules (always included)
        rules = self.get_project_rules_prompt()
        if rules:
            parts.append(rules)

        # L3: Semantic results (ranked by M_score)
        results = self.semantic_search(query, top_k=top_k)
        if results:
            sections = []
            for r in results:
                fp = r.get("file_path", "unknown")
                text = r.get("text", "")
                score = r.get("m_score", 0.0)
                sections.append(f"[{fp}] (score: {score:.3f}):\n{text}")
            parts.append(f"## Relevant Code Context\n"
                         f"Retrieved {len(sections)} relevant chunks:\n\n"
                         + "\n---\n".join(sections))

        # L2: Recent conversation summary
        summary = self.get_conversation_summary()
        if summary:
            parts.append(f"## Recent Context Summary\n{summary}")

        # L1: Working memory (recent files)
        recent_file = self.working_get("recent_file")
        if recent_file:
            parts.append(f"## Currently Editing\n{recent_file}")

        return "\n\n".join(parts)

    # ── Change Detection ────────────────────────────────────────────

    def _start_change_detector(self) -> None:
        """Start the file change detector (L3 incremental indexing)."""
        if not self._hash_cache:
            return

        self._detector = PollingChangeDetector(
            project_path=self._project_path,
            cache=self._hash_cache,
            ignore_patterns=self._ignore_patterns,
            poll_interval=5.0,
        )
        self._detector.on_change(self._on_file_changed)
        self._detector.start()
        self._watcher_running = True

    def _stop_change_detector(self) -> None:
        """Stop the change detector."""
        if self._detector:
            self._detector.stop()
            self._detector = None
        self._watcher_running = False

    def _on_file_changed(self, file_path: str, event_type: str) -> None:
        """Callback for file changes — triggers re-indexing.

        Args:
            file_path: Changed file path.
            event_type: 'created', 'modified', or 'deleted'.
        """
        if event_type in ("created", "modified"):
            logger.info("File changed: %s (%s) — triggering re-index",
                        file_path, event_type)
            self.index_file(file_path)
        elif event_type == "deleted":
            logger.info("File deleted: %s", file_path)
            # Could add semantic deletion by path here

    # ── Memory Consolidation ────────────────────────────────────────

    def consolidate(self) -> None:
        """Consolidate memories using M_score.

        Saves mscore state and removes stale working memory entries.
        """
        # Clean expired working memory
        expired = self._working_memory.clear_expired()
        if expired:
            logger.info("WorkingMemory: cleared %d expired entries", expired)

        # Save mscore state
        mscore_path = self._base_data_dir / MSCORE_STATE_NAME
        self._mscore.persist_state(str(mscore_path))

    # ── Properties ──────────────────────────────────────────────────

    @property
    def project_path(self) -> str:
        """Current project path."""
        return self._project_path

    @property
    def watcher_running(self) -> bool:
        """Whether the change detector is running."""
        return self._watcher_running

    @property
    def has_project_rules(self) -> bool:
        """Whether project rules are loaded."""
        return self._procedural.has_rules

    def __del__(self) -> None:
        """Cleanup on garbage collection."""
        try:
            self.close_project()
        except Exception:
            pass
