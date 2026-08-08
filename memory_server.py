"""
KinnyCode — Memory Server (FastAPI + LanceDB)

Multi-layer persistent memory:
  Layer 1 (Short):  conversation_history  — per-session agent conversations
  Layer 2 (Medium): architecture_decisions — refactor & design decisions
  Layer 3 (Long):   project_codebase      — indexed code chunks for RAG

Embeddings: sentence-transformers (all-MiniLM-L6-v2, dim 384)
Storage:      LanceDB embedded (zero-config, local disk)

Run with: uvicorn memory_server:app --host 127.0.0.1 --port 8006
"""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import lancedb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from lancedb.pydantic import LanceModel, Vector
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

from memory.embedding_cache import EmbeddingCache
from memory.indexation_service import IndexationService
from memory.monitoring import router as monitoring_router, track_indexing, track_search
from memory.validation import validate_project_id

app = FastAPI(title="KinnyCode — Multi-Layer Memory System (LanceDB)")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include monitoring router
app.include_router(monitoring_router)

# ═══════════════════════════════════════════════════════════════════
#  Embedding model (local, CPU-only — cross-platform compatible)
# ═══════════════════════════════════════════════════════════════════
_EMBED_MODEL: SentenceTransformer | None = None


def _get_embed_model() -> SentenceTransformer:
    """Lazy-load the sentence-transformers embedding model (all-MiniLM-L6-v2)."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _EMBED_MODEL


# Embedding dimension for all-MiniLM-L6-v2
_EMBED_DIM = 384

# ═══════════════════════════════════════════════════════════════════
#  Embedding Cache (TTL-based)
# ═══════════════════════════════════════════════════════════════════
_embedding_cache = EmbeddingCache(ttl=3600, max_size=10000)


def _embed_with_cache(docs: list[str]) -> list[list[float]]:
    """Embed documents using cache when available.
    
    Args:
        docs: List of text documents to embed.
        
    Returns:
        List of embedding vectors.
    """
    results = [None] * len(docs)
    miss_indices = []
    
    # Check cache for each document
    for i, doc in enumerate(docs):
        cached = _embedding_cache.get(doc)
        if cached is not None:
            results[i] = cached
        else:
            miss_indices.append(i)
    
    # Compute embeddings for cache misses
    if miss_indices:
        miss_docs = [docs[i] for i in miss_indices]
        model = _get_embed_model()
        new_embeddings = model.encode(miss_docs, normalize_embeddings=True).tolist()
        
        # Store in cache and fill results
        for idx, embedding in zip(miss_indices, new_embeddings):
            _embedding_cache.set(docs[idx], embedding)
            results[idx] = embedding
    
    return results


# ═══════════════════════════════════════════════════════════════════
#  LanceDB database & table schemas
# ═══════════════════════════════════════════════════════════════════
db_path = Path("./lancedb_memory_db")
db = lancedb.connect(str(db_path))


class CodeChunk(LanceModel):
    """Layer 3 — Code chunk with vector embedding."""
    id: str
    document: str
    file_path: str
    language: str
    content_hash: str
    project_id: str = ""
    vector: Vector(_EMBED_DIM)


class Decision(LanceModel):
    """Layer 2 — Architecture / refactor decision."""
    id: str
    document: str
    type: str
    project_id: str = ""
    vector: Vector(_EMBED_DIM)


class ConversationChunk(LanceModel):
    """Layer 1 — Conversation turn with vector embedding."""
    id: str
    document: str
    session_id: str
    role: str
    turn: int
    project_id: str = ""
    vector: Vector(_EMBED_DIM)


def _get_embedding_func():
    from lancedb.embeddings import get_registry
    return get_registry().get("sentence-transformers").create(
        name="all-MiniLM-L6-v2", device="cpu"
    )


def _ensure_table(name: str, schema, source_column: str = "document"):
    if name in db.table_names():
        return db.open_table(name)
    try:
        ef = _get_embedding_func()
        return db.create_table(name, schema=schema, embedding_functions=[{
            "source_column": source_column,
            "function": ef,
            "vector_column": "vector",
        }])
    except Exception:
        return db.create_table(name, schema=schema)


code_table = _ensure_table("project_codebase", CodeChunk)
arch_table = _ensure_table("architecture_decisions", Decision)
conv_table = _ensure_table("conversation_history", ConversationChunk)


class DocumentChunk(LanceModel):
    """Layer 4 — Document/book chunk with vector embedding."""
    id: str
    document: str
    source_file: str
    doc_type: str
    chunk_index: int
    page_number: int | None = None
    content_hash: str
    project_id: str = ""
    vector: Vector(_EMBED_DIM)


doc_table = _ensure_table("documents", DocumentChunk)


class AgentTask(LanceModel):
    """Layer 5 — Agent task with vector embedding."""
    id: str
    document: str
    task_title: str
    task_status: str
    task_priority: str
    task_dependencies: str = ""
    project_id: str = ""
    created_at: str
    updated_at: str
    vector: Vector(_EMBED_DIM)


task_table = _ensure_table("agent_tasks", AgentTask)


# ═══════════════════════════════════════════════════════════════════
#  Pydantic request models
# ═══════════════════════════════════════════════════════════════════
class CodeDocument(BaseModel):
    file_path: str
    content: str
    language: str
    content_hash: str | None = None
    project_id: str | None = None


class QueryModel(BaseModel):
    prompt: str
    n_results: int = 4
    project_id: str | None = None


class MemoryEntry(BaseModel):
    key_decision: str
    context: str
    project_id: str | None = None


class ConversationSave(BaseModel):
    session_id: str
    messages: list[dict]   # [{"role":"...", "content":"..."}, ...]
    summarise: bool = False
    project_id: str | None = None


class ConversationLoad(BaseModel):
    session_id: str
    limit: int = 20
    summary_only: bool = False
    project_id: str | None = None


class BatchIndexRequest(BaseModel):
    files: list[dict]  # [{"file_path":"...", "content":"...", "language":"..."}, ...]
    clear_first: bool = False
    project_id: str | None = None


class DocumentIndexRequest(BaseModel):
    file_path: str
    doc_type: str | None = None  # Auto-detect if None
    chunk_size: int = 1000
    chunk_overlap: int = 200
    project_id: str | None = None


class DocumentSearchRequest(BaseModel):
    query: str
    n_results: int = 5
    doc_type: str | None = None  # Filter by type if set
    project_id: str | None = None


class BatchDocumentRequest(BaseModel):
    file_paths: list[str]
    clear_first: bool = False
    project_id: str | None = None


class TaskUpsertRequest(BaseModel):
    task_id: str | None = None
    title: str
    description: str = ""
    context: str = ""
    status: str = "pending"
    priority: str = "medium"
    dependencies: list[str] = []
    project_id: str | None = None


class TaskListRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    project_id: str | None = None


class TaskSearchRequest(BaseModel):
    query: str
    n_results: int = 5
    status: str | None = None
    project_id: str | None = None


class SessionContextRequest(BaseModel):
    project_id: str | None = None
    include_tasks: bool = True
    include_decisions: bool = True
    include_code: bool = False
    include_documents: bool = False
    n_results: int = 5


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════
def _split_text(content: str, language: str, *, chunk_size: int = 1500, chunk_overlap: int = 200) -> list[str]:
    """
    Simple recursive text splitter.

    Attempts language-specific splitting via langchain_text_splitters
    when available; falls back to generic splitting otherwise.
    """
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        try:
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=language,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        except ValueError:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
            )
        return splitter.split_text(content)
    except ImportError:
        # Fallback: generic splitting with common delimiters
        return _generic_split(content, chunk_size, chunk_overlap)


def _generic_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Generic character-based text splitter."""
    if not text.strip():
        return []

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a natural boundary within the chunk
        for sep in ["\n\n", "\n", ". ", "? ", "! "]:
            last = chunk.rfind(sep)
            if last > chunk_size * 0.4:  # Only use if separator is past 40% of chunk
                chunk = chunk[: last + len(sep)]
                break

        chunks.append(chunk.strip())
        start = start + chunk_size - chunk_overlap

    return [c for c in chunks if c]


def _embed_documents(docs: list[str]) -> list[list[float]]:
    """Embed a list of documents using the local sentence-transformers model."""
    model = _get_embed_model()
    return model.encode(docs, normalize_embeddings=True).tolist()


def _delete_by_file_path(table: Any, file_path: str, project_id: str = "") -> None:
    """Delete all rows matching a file_path."""
    try:
        # Try metadata-filtered search first (fast path)
        try:
            df = table.search().where(f"file_path = '{file_path}'").limit(10000).to_pandas()
        except TypeError:
            # .search() without query not supported — fallback to full read + filter
            df = table.to_pandas()
            df = df[df["file_path"] == file_path]

        if project_id:
            df = df[df["project_id"] == project_id]
        if not df.empty:
            ids = [row["id"] for row in df[["id"]].itertuples(index=False)]
            if ids:
                table.delete(f"id IN ({', '.join(repr(i) for i in ids)})")
    except Exception:
        pass


def _delete_by_session_id(table: Any, session_id: str) -> None:
    """Delete all rows matching a session_id."""
    try:
        # Try metadata-filtered search first (fast path)
        try:
            df = table.search().where(f"session_id = '{session_id}'").limit(10000).to_pandas()
        except TypeError:
            # .search() without query not supported — fallback to full read + filter
            df = table.to_pandas()
            df = df[df["session_id"] == session_id]

        if not df.empty:
            ids = [row["id"] for row in df[["id"]].itertuples(index=False)]
            if ids:
                table.delete(f"id IN ({', '.join(repr(i) for i in ids)})")
    except Exception:
        pass


def _get_first_row(table: Any, filter_col: str, filter_val: str, project_id: str = "") -> dict | None:
    """Get the first row matching a column value, or None."""
    try:
        df = table.search().where(f"{filter_col} = '{filter_val}'").limit(1).to_pandas()
        if not df.empty:
            if project_id:
                df = df[df["project_id"] == project_id]
            if not df.empty:
                return dict(df.iloc[0])
        return None
    except TypeError:
        df = table.to_pandas()
        mask = df[filter_col] == filter_val
        if project_id:
            mask = mask & (df["project_id"] == project_id)
        if mask.any():
            return dict(df[mask].iloc[0])
        return None
    except Exception:
        return None


def _delete_by_source_file(table: Any, source_file: str, project_id: str = "") -> None:
    """Delete all rows matching a source_file in the documents table."""
    try:
        try:
            df = table.search().where(f"source_file = '{source_file}'").limit(10000).to_pandas()
        except TypeError:
            df = table.to_pandas()
            df = df[df["source_file"] == source_file]
        if project_id:
            df = df[df["project_id"] == project_id]
        if not df.empty:
            ids = [row["id"] for row in df[["id"]].itertuples(index=False)]
            if ids:
                table.delete(f"id IN ({', '.join(repr(i) for i in ids)})")
    except Exception:
        pass


def _resolve_project_id(req_project_id: str | None) -> str:
    """Resolve project_id from request or default to empty string."""
    return req_project_id or ""


def _delete_by_project_id(table: Any, project_id: str) -> None:
    """Delete all rows matching a project_id."""
    if not project_id:
        return
    try:
        try:
            df = table.search().where(f"project_id = '{project_id}'").limit(100000).to_pandas()
        except TypeError:
            df = table.to_pandas()
            df = df[df["project_id"] == project_id]
        if not df.empty:
            ids = [row["id"] for row in df[["id"]].itertuples(index=False)]
            if ids:
                table.delete(f"id IN ({', '.join(repr(i) for i in ids)})")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  Indexation Service (consolidates duplicated indexing logic)
# ═══════════════════════════════════════════════════════════════════
indexation_service = IndexationService(
    db=db,
    embed_func=_embed_with_cache,
    split_func=_split_text,
)


# ═══════════════════════════════════════════════════════════════════
#  Layer 3 — Codebase Indexing (Long-term RAG)
# ═══════════════════════════════════════════════════════════════════
@app.post("/index-file")
async def index_file(doc: CodeDocument):
    """Index a single code file into the codebase table."""
    try:
        pid = validate_project_id(doc.project_id)
        track_indexing()
        
        result = indexation_service.index_code_chunks(
            table=code_table,
            file_path=doc.file_path,
            content=doc.content,
            language=doc.language,
            project_id=pid,
            content_hash=doc.content_hash,
        )
        
        return {
            "status": "success",
            "chunks_indexed": result["chunks_indexed"],
            "content_hash": result["content_hash"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reindex-file")
async def reindex_file(doc: CodeDocument):
    """Re-index a file only if content_hash has changed or is not provided."""
    pid = _resolve_project_id(doc.project_id)
    if doc.content_hash:
        row = _get_first_row(code_table, "file_path", doc.file_path, project_id=pid)
        if row:
            stored_hash = row.get("content_hash", "")
            if stored_hash and stored_hash == doc.content_hash:
                return {
                    "status": "skipped",
                    "reason": "Content unchanged — hash matches",
                    "content_hash": doc.content_hash,
                }

    return await index_file(doc)


@app.post("/index-project")
async def index_project(req: BatchIndexRequest):
    """Batch-index multiple files at once. Optionally clears the codebase first."""
    try:
        pid = validate_project_id(req.project_id)
        track_indexing()
        
        result = indexation_service.index_batch_files(
            table=code_table,
            files=req.files,
            project_id=pid,
            clear_first=req.clear_first,
        )
        
        return {
            "status": "success",
            "files_indexed": result["files_indexed"],
            "chunks_indexed": result["chunks_indexed"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
#  Index by file paths — server reads files from disk
# ═══════════════════════════════════════════════════════════════════

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python", ".pyx": "python",
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".rs": "rust", ".go": "go", ".java": "java", ".kt": "kotlin",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".swift": "swift", ".scala": "scala",
    ".sh": "bash", ".ps1": "powershell", ".sql": "sql",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".json": "json", ".xml": "xml", ".vue": "vue", ".svelte": "svelte",
    ".tf": "hcl", ".lua": "lua", ".r": "r", ".graphql": "graphql",
    ".dockerfile": "dockerfile", ".tex": "latex",
}

_MAX_FILE_SIZE = 1_048_576


def _detect_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    return _LANGUAGE_MAP.get(suffix, "text")


class FilePathsIndexRequest(BaseModel):
    file_paths: list[str]
    clear_first: bool = False
    project_id: str | None = None


@app.post("/index-file-paths")
async def index_file_paths(req: FilePathsIndexRequest):
    try:
        pid = _resolve_project_id(req.project_id)
        if req.clear_first:
            _delete_by_project_id(code_table, pid)

        total_indexed = 0
        total_chunks = 0
        errors: list[dict] = []

        for file_path in req.file_paths:
            try:
                p = Path(file_path)
                if not p.is_file():
                    errors.append({"file_path": file_path, "error": "File not found"})
                    continue
                if p.stat().st_size > _MAX_FILE_SIZE:
                    errors.append({"file_path": file_path, "error": "File exceeds 1 MB limit"})
                    continue
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    errors.append({"file_path": file_path, "error": "Cannot read file"})
                    continue
                if not content.strip():
                    continue

                language = _detect_language(file_path)
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                chunks = _split_text(content, language)
                if not chunks:
                    continue

                _delete_by_file_path(code_table, file_path, project_id=pid)
                vectors = _embed_documents(chunks)
                ids = [f"{file_path}_chunk_{i}" for i in range(len(chunks))]
                data = [
                    {
                        "id": ids[i], "document": chunks[i],
                        "file_path": file_path, "language": language,
                        "content_hash": content_hash, "project_id": pid,
                        "vector": vectors[i],
                    }
                    for i in range(len(chunks))
                ]
                code_table.add(data)
                total_indexed += 1
                total_chunks += len(chunks)
            except Exception as e:
                errors.append({"file_path": file_path, "error": str(e)})

        return {
            "status": "success",
            "files_indexed": total_indexed,
            "chunks_indexed": total_chunks,
            "errors": errors,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
#  Layer 2 — Architecture Decisions (Medium-term memory)
# ═══════════════════════════════════════════════════════════════════
@app.post("/remember-decision")
async def remember_decision(entry: MemoryEntry):
    """Store a design/refactoring decision."""
    pid = _resolve_project_id(entry.project_id)
    decision_id = str(uuid.uuid4())
    doc = f"Decisi\u00f3n: {entry.key_decision} | Contexto: {entry.context}"
    vectors = _embed_documents([doc])
    arch_table.add([{
        "id": decision_id,
        "document": doc,
        "type": "refactor_decision",
        "project_id": pid,
        "vector": vectors[0],
    }])
    return {"status": "saved", "id": decision_id}


# ═══════════════════════════════════════════════════════════════════
#  Layer 1 — Conversation History (Short-term session memory)
# ═══════════════════════════════════════════════════════════════════
@app.post("/save-conversation")
async def save_conversation(conv: ConversationSave):
    """Persist agent conversation turns."""
    try:
        pid = _resolve_project_id(conv.project_id)
        ids = []
        documents = []
        roles = []
        turns = []

        for i, msg in enumerate(conv.messages):
            content = msg.get("content", "").strip()
            if not content:
                continue
            ids.append(f"{conv.session_id}_turn_{i}")
            documents.append(f"[{msg.get('role', 'unknown')}]: {content}")
            roles.append(msg.get("role", ""))
            turns.append(i)

        if documents:
            # Remove old turns for this session
            _delete_by_session_id(conv_table, conv.session_id)

            vectors = _embed_documents(documents)
            data = [
                {
                    "id": ids[i],
                    "document": documents[i],
                    "session_id": conv.session_id,
                    "role": roles[i],
                    "turn": turns[i],
                    "project_id": pid,
                    "vector": vectors[i],
                }
                for i in range(len(documents))
            ]
            conv_table.add(data)

        return {"status": "saved", "turns": len(documents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load-conversation")
async def load_conversation(req: ConversationLoad):
    """Load recent conversation turns for a session."""
    try:
        pid = _resolve_project_id(req.project_id)
        if req.summary_only:
            try:
                try:
                    df = conv_table.search().where(f"session_id = '{req.session_id}'").to_pandas()
                except TypeError:
                    df = conv_table.to_pandas()
                    df = df[df["session_id"] == req.session_id]
                if pid:
                    df = df[df["project_id"] == pid]
                if not df.empty:
                    docs = df["document"].tolist()[-5:]  # last 5 turns
                    return {
                        "session_id": req.session_id,
                        "summary": "\n".join(docs),
                        "messages": [],
                    }
            except Exception:
                pass
            return {"session_id": req.session_id, "summary": "", "messages": []}

        # Load full conversation
        try:
            try:
                df = conv_table.search().where(f"session_id = '{req.session_id}'").to_pandas()
            except TypeError:
                df = conv_table.to_pandas()
                df = df[df["session_id"] == req.session_id]
            if pid:
                df = df[df["project_id"] == pid]
            if not df.empty:
                messages = []
                for _, row in df.iterrows():
                    raw = row["document"]
                    role = row["role"]
                    content = raw.replace(f"[{role}]: ", "", 1) if role else raw
                    messages.append({"role": role, "content": content})
                return {
                    "session_id": req.session_id,
                    "messages": messages[-req.limit:],
                    "summary": "",
                }
        except Exception:
            pass

        return {"session_id": req.session_id, "messages": [], "summary": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
#  Search helper — manual embedding for reliable vector search
# ═══════════════════════════════════════════════════════════════════

def _search_table(table, query_text: str, limit: int = 5):
    qv = _embed_documents([query_text])[0]
    return table.search(qv).limit(limit).to_pandas()


# ═══════════════════════════════════════════════════════════════════
#  RAG — Cross-layer context retrieval
# ═══════════════════════════════════════════════════════════════════
@app.post("/retrieve-context")
async def retrieve_context(query: QueryModel):
    """Retrieve relevant context from all memory layers."""
    pid = validate_project_id(query.project_id)
    track_search()
    extracted_context = "--- CONTEXTO RELEVANTE RECUPERADO (RAG) ---\n\n"

    # ── Conversation history ──────────────────────────────────────
    try:
        results = _search_table(conv_table, query.prompt, limit=2)
        if pid:
            results = results[results["project_id"] == pid]
        if not results.empty:
            extracted_context += "### Historial de Conversacion Relevante:\n"
            for doc in results["document"].tolist():
                extracted_context += f"- {doc[:300]}\n"
            extracted_context += "\n"
    except Exception:
        pass

    # ── Architecture decisions ────────────────────────────────────
    try:
        results = _search_table(arch_table, query.prompt, limit=2)
        if pid:
            results = results[results["project_id"] == pid]
        if not results.empty:
            extracted_context += "### Decisiones de Arquitectura previas:\n"
            for doc in results["document"].tolist():
                extracted_context += f"- {doc}\n"
            extracted_context += "\n"
    except Exception:
        pass

    # ── Codebase ──────────────────────────────────────────────────
    try:
        results = _search_table(code_table, query.prompt, limit=query.n_results)
        if pid:
            results = results[results["project_id"] == pid]
        if not results.empty:
            extracted_context += "### Fragmentos de Codigo relacionados:\n"
            for _, row in results.iterrows():
                extracted_context += f"// Archivo: {row['file_path']}\n{row['document']}\n\n"
    except Exception:
        pass

    # ── Documents ──────────────────────────────────────────────────
    try:
        results = _search_table(doc_table, query.prompt, limit=2)
        if pid:
            results = results[results["project_id"] == pid]
        if not results.empty:
            extracted_context += "### Documentos y Referencias:\n"
            for _, row in results.iterrows():
                src = row.get("source_file", "unknown")
                doc_type = row.get("doc_type", "txt")
                extracted_context += f"- [{doc_type}] {src}: {row['document'][:400]}\n"
            extracted_context += "\n"
    except Exception:
        pass

    return {"context": extracted_context}


# ═══════════════════════════════════════════════════════════════════
#  Semantic Search (for UI search panel)
# ═══════════════════════════════════════════════════════════════════
@app.post("/semantic-search")
async def semantic_search(query: QueryModel):
    pid = validate_project_id(query.project_id)
    track_search()
    results = []
    try:
        df = _search_table(code_table, query.prompt, limit=query.n_results)
        if pid:
            df = df[df["project_id"] == pid]
        if not df.empty:
            dist_col = "_distance" if "_distance" in df.columns else "distance"
            for _, row in df.iterrows():
                dist = row.get(dist_col, None)
                results.append({
                    "file_path": row["file_path"],
                    "language": row["language"],
                    "snippet": row["document"][:500],
                    "score": round(1.0 - dist, 4) if dist is not None else 1.0,
                })
    except Exception:
        pass
    return {"query": query.prompt, "results": results}


# ═══════════════════════════════════════════════════════════════════
#  Layer 4 — Document & Book RAG
# ═══════════════════════════════════════════════════════════════════
@app.post("/index-document")
async def index_document(req: DocumentIndexRequest):
    """Ingest a document (PDF, TXT, etc.) and index its chunks for RAG."""
    try:
        from memory.document_loader import DocumentIngestor
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Document loading dependencies not installed. Install PyPDF2/pdfplumber.",
        )

    try:
        pid = validate_project_id(req.project_id)
        track_indexing()
        ingestor = DocumentIngestor(
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
        if req.doc_type:
            from memory.document_loader import DocumentChunker
            chunker = DocumentChunker(chunk_size=req.chunk_size, chunk_overlap=req.chunk_overlap)
            ext_type = DocumentIngestor._detect_type(Path(req.file_path))
            if req.doc_type != ext_type:
                chunks = chunker.chunk_texts(
                    [Path(req.file_path).read_text(encoding="utf-8", errors="replace")],
                    source_file=req.file_path,
                    doc_type=req.doc_type,
                )
            else:
                chunks = ingestor.ingest(req.file_path)
        else:
            chunks = ingestor.ingest(req.file_path)

        if not chunks:
            return {"status": "success", "source_file": req.file_path, "doc_type": req.doc_type or "unknown", "chunks_indexed": 0}

        # Delete old chunks for this source file
        _delete_by_source_file(doc_table, req.file_path)

        # Use IndexationService for batch embedding and insertion
        result = indexation_service.index_document_chunks(
            table=doc_table,
            chunks=chunks,
            project_id=pid,
        )

        return {
            "status": "success",
            "source_file": req.file_path,
            "doc_type": chunks[0].get("doc_type", req.doc_type or "unknown"),
            "chunks_indexed": result["chunks_indexed"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Document loading dependencies not installed. Install PyPDF2/pdfplumber.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load-book")
async def load_book(req: DocumentIndexRequest):
    """Load and index a book (same as /index-document with a descriptive name)."""
    try:
        from memory.document_loader import DocumentIngestor
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Document loading dependencies not installed. Install PyPDF2/pdfplumber.",
        )

    try:
        pid = validate_project_id(req.project_id)
        track_indexing()
        ingestor = DocumentIngestor(
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
        )
        if req.doc_type:
            from memory.document_loader import DocumentChunker
            chunker = DocumentChunker(chunk_size=req.chunk_size, chunk_overlap=req.chunk_overlap)
            ext_type = DocumentIngestor._detect_type(Path(req.file_path))
            if req.doc_type != ext_type:
                chunks = chunker.chunk_texts(
                    [Path(req.file_path).read_text(encoding="utf-8", errors="replace")],
                    source_file=req.file_path,
                    doc_type=req.doc_type,
                )
            else:
                chunks = ingestor.ingest(req.file_path)
        else:
            chunks = ingestor.ingest(req.file_path)

        if not chunks:
            return {"status": "success", "source_file": req.file_path, "doc_type": req.doc_type or "unknown", "chunks_indexed": 0}

        # Delete old chunks for this source file
        _delete_by_source_file(doc_table, req.file_path)

        # Use IndexationService for batch embedding and insertion
        result = indexation_service.index_document_chunks(
            table=doc_table,
            chunks=chunks,
            project_id=pid,
        )

        return {
            "status": "success",
            "source_file": req.file_path,
            "doc_type": chunks[0].get("doc_type", req.doc_type or "unknown"),
            "chunks_indexed": result["chunks_indexed"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Document loading dependencies not installed. Install PyPDF2/pdfplumber.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search-documents")
async def search_documents(req: DocumentSearchRequest):
    """Semantic search across indexed documents with optional doc_type filter."""
    try:
        pid = validate_project_id(req.project_id)
        track_search()
        df = _search_table(doc_table, req.query, limit=req.n_results * 2)

        if pid:
            df = df[df["project_id"] == pid]

        if req.doc_type and not df.empty:
            df = df[df["doc_type"] == req.doc_type]

        if df.empty:
            return {"results": []}

        # Take top n_results after filtering
        df = df.head(req.n_results)

        dist_col = "_distance" if "_distance" in df.columns else "distance"
        results = []
        for _, row in df.iterrows():
            dist = row.get(dist_col, None)
            page = row.get("page_number")
            results.append({
                "source_file": row["source_file"],
                "doc_type": row["doc_type"],
                "snippet": row["document"][:500],
                "page_number": int(page) if page is not None and not (isinstance(page, float) and str(page) == "nan") else None,
                "score": round(1.0 - dist, 4) if dist is not None else 1.0,
            })

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list-documents")
async def list_documents(project_id: str | None = None):
    """List all indexed documents grouped by source file."""
    try:
        pid = _resolve_project_id(project_id)
        df = doc_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        if df.empty:
            return {"documents": []}

        grouped = df.groupby("source_file").agg(
            doc_type=("doc_type", "first"),
            chunks=("id", "count"),
            total_chars=("document", lambda x: sum(len(s) for s in x)),
        ).reset_index()

        documents = []
        for _, row in grouped.iterrows():
            documents.append({
                "source_file": row["source_file"],
                "doc_type": row["doc_type"],
                "chunks": int(row["chunks"]),
                "total_chars": int(row["total_chars"]),
            })

        return {"documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list-projects")
async def list_projects():
    """List all project IDs with document counts."""
    try:
        df = doc_table.to_pandas()
        if df.empty:
            return {"projects": []}

        projects = df.groupby("project_id").agg(
            documents=("source_file", "nunique"),
            chunks=("id", "count"),
            total_chars=("document", lambda x: sum(len(s) for s in x)),
        ).reset_index()

        result = []
        for _, row in projects.iterrows():
            result.append({
                "project_id": row["project_id"],
                "documents": int(row["documents"]),
                "chunks": int(row["chunks"]),
                "total_chars": int(row["total_chars"]),
            })

        return {"projects": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/delete-document")
async def delete_document(source_file: str, project_id: str | None = None):
    """Delete all chunks for a given source file."""
    try:
        pid = _resolve_project_id(project_id)
        _delete_by_source_file(doc_table, source_file, project_id=pid)
        return {"status": "deleted", "source_file": source_file}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/index-documents-batch")
async def index_documents_batch(req: BatchDocumentRequest):
    """Batch-index multiple documents at once. Optionally clears the documents table first."""
    try:
        from memory.document_loader import DocumentIngestor
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Document loading dependencies not installed. Install PyPDF2/pdfplumber.",
        )

    try:
        pid = validate_project_id(req.project_id)
        track_indexing()
        if req.clear_first:
            try:
                if pid:
                    _delete_by_project_id(doc_table, pid)
                else:
                    df = doc_table.to_pandas()
                    if not df.empty:
                        ids = [row["id"] for row in df[["id"]].itertuples(index=False)]
                        if ids:
                            doc_table.delete(f"id IN ({', '.join(repr(i) for i in ids)})")
            except Exception:
                pass

        results = []
        ingestor = DocumentIngestor()

        for file_path in req.file_paths:
            try:
                if not Path(file_path).exists():
                    results.append({"file_path": file_path, "status": "error", "error": "File not found"})
                    continue

                chunks = ingestor.ingest(file_path)

                if not chunks:
                    results.append({"file_path": file_path, "status": "success", "chunks_indexed": 0})
                    continue

                # Delete old chunks for this source file
                _delete_by_source_file(doc_table, file_path)

                # Use IndexationService for batch embedding and insertion
                result = indexation_service.index_document_chunks(
                    table=doc_table,
                    chunks=chunks,
                    project_id=pid,
                )
                results.append({"file_path": file_path, "status": "success", "chunks_indexed": result["chunks_indexed"]})
            except Exception as ex:
                results.append({"file_path": file_path, "status": "error", "error": str(ex)})

        return {"status": "completed", "results": results}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
#  Multi-project namespace support
# ═══════════════════════════════════════════════════════════════════
class ProjectInfoRequest(BaseModel):
    project_id: str | None = None


@app.post("/project-info")
async def project_info(req: ProjectInfoRequest):
    """Get statistics about a project's indexed data."""
    try:
        pid = validate_project_id(req.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    stats = {}

    # Count code chunks
    try:
        df = code_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        stats["code_chunks"] = len(df)
    except Exception:
        stats["code_chunks"] = 0

    # Count documents
    try:
        df = doc_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        stats["document_chunks"] = len(df)
    except Exception:
        stats["document_chunks"] = 0

    # Count conversations
    try:
        df = conv_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        stats["conversations"] = len(df)
    except Exception:
        stats["conversations"] = 0

    # Count decisions
    try:
        df = arch_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        stats["decisions"] = len(df)
    except Exception:
        stats["decisions"] = 0

    # Count tasks
    try:
        df = task_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        stats["tasks"] = len(df)
    except Exception:
        stats["tasks"] = 0

    return {"project_id": pid, "stats": stats}


@app.post("/clear-project")
async def clear_project(req: ProjectInfoRequest):
    """Clear all data for a specific project."""
    try:
        pid = validate_project_id(req.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not pid:
        raise HTTPException(status_code=400, detail="project_id is required")

    _delete_by_project_id(code_table, pid)
    _delete_by_project_id(doc_table, pid)
    _delete_by_project_id(conv_table, pid)
    _delete_by_project_id(arch_table, pid)
    _delete_by_project_id(task_table, pid)

    return {"status": "cleared", "project_id": pid}


# ═══════════════════════════════════════════════════════════════════
#  Layer 5 — Agent Task Working Set
# ═══════════════════════════════════════════════════════════════════

@app.post("/tasks/upsert")
async def task_upsert(req: TaskUpsertRequest):
    """Create or update an agent task with semantic embedding."""
    try:
        pid = validate_project_id(req.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    now = datetime.utcnow().isoformat()

    doc = (
        f"title: {req.title} | description: {req.description} | "
        f"status: {req.status} | priority: {req.priority} | context: {req.context}"
    )
    deps_str = json.dumps(req.dependencies or [])

    if req.task_id:
        task_id = req.task_id
        _delete_by_id(task_table, task_id)
        created = now
    else:
        task_id = str(uuid.uuid4())
        created = now

    vectors = _embed_documents([doc])
    task_table.add([{
        "id": task_id,
        "document": doc,
        "task_title": req.title,
        "task_status": req.status,
        "task_priority": req.priority,
        "task_dependencies": deps_str,
        "project_id": pid,
        "created_at": created,
        "updated_at": now,
        "vector": vectors[0],
    }])

    _bump_task_access(task_id)

    return {
        "status": "saved",
        "task_id": task_id,
        "title": req.title,
    }


@app.get("/tasks")
async def task_list(
    status: str | None = None,
    priority: str | None = None,
    project_id: str | None = None,
):
    """List agent tasks with optional filters."""
    try:
        pid = validate_project_id(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        df = task_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        if status:
            df = df[df["task_status"] == status]
        if priority:
            df = df[df["task_priority"] == priority]
        if df.empty:
            return {"tasks": [], "count": 0}

        df = df.sort_values("updated_at", ascending=False)
        tasks = []
        for _, row in df.iterrows():
            deps = []
            try:
                deps = json.loads(row.get("task_dependencies", "[]"))
            except (json.JSONDecodeError, TypeError):
                deps = []
            tasks.append({
                "id": row["id"],
                "title": row["task_title"],
                "status": row["task_status"],
                "priority": row["task_priority"],
                "dependencies": deps,
                "description": row["document"],
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            })
        return {"tasks": tasks, "count": len(tasks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks/{task_id}")
async def task_get(task_id: str):
    """Get a single task by ID."""
    row = _get_first_row(task_table, "id", task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    deps = []
    try:
        deps = json.loads(row.get("task_dependencies", "[]"))
    except (json.JSONDecodeError, TypeError):
        deps = []
    return {
        "id": row["id"],
        "title": row["task_title"],
        "status": row["task_status"],
        "priority": row["task_priority"],
        "dependencies": deps,
        "description": row["document"],
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


@app.delete("/tasks/{task_id}")
async def task_delete(task_id: str):
    """Delete a task."""
    try:
        task_table.delete(f"id = '{task_id}'")
        return {"status": "deleted", "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tasks/search")
async def task_search(req: TaskSearchRequest):
    """Semantic search for agent tasks."""
    try:
        pid = validate_project_id(req.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    track_search()
    try:
        results = _search_table(task_table, req.query, limit=req.n_results)
        if pid:
            results = results[results["project_id"] == pid]
        if req.status:
            results = results[results["task_status"] == req.status]

        tasks = []
        if not results.empty:
            dist_col = "_distance" if "_distance" in results.columns else "distance"
            for _, row in results.iterrows():
                deps = []
                try:
                    deps = json.loads(row.get("task_dependencies", "[]"))
                except (json.JSONDecodeError, TypeError):
                    deps = []
                dist = row.get(dist_col, None)
                tasks.append({
                    "id": row["id"],
                    "title": row["task_title"],
                    "status": row["task_status"],
                    "priority": row["task_priority"],
                    "dependencies": deps,
                    "snippet": row["document"][:400],
                    "score": round(1.0 - dist, 4) if dist is not None else 1.0,
                })
        return {"query": req.query, "results": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _delete_by_id(table: Any, row_id: str) -> None:
    """Delete a single row by id."""
    try:
        table.delete(f"id = '{row_id}'")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  Proactive Memory Push — Session Context Injection
# ═══════════════════════════════════════════════════════════════════

@app.post("/session-context")
async def session_context(req: SessionContextRequest):
    """Proactive context push for agent sessions.

    Returns a condensed context block with pending tasks, recent
    decisions, and optionally related code — designed to be injected
    into the agent's system prompt at session start.
    """
    try:
        pid = validate_project_id(req.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ctx = ""

    if req.include_tasks:
        try:
            df = task_table.to_pandas()
            if pid:
                df = df[df["project_id"] == pid]
            pending = df[df["task_status"].isin(["pending", "in_progress"])]
            if not pending.empty:
                pending = pending.sort_values("updated_at", ascending=False)
                ctx += "### Tareas Pendientes del Proyecto:\n"
                for _, row in pending.iterrows():
                    p = row["task_priority"]
                    s = row["task_status"]
                    ctx += f"- [{p}/{s}] {row['task_title']}\n"
                ctx += "\n"
        except Exception:
            pass

    if req.include_decisions:
        try:
            df = arch_table.to_pandas()
            if pid:
                df = df[df["project_id"] == pid]
            if not df.empty:
                ctx += "### Decisiones de Arquitectura Recientes:\n"
                recent = df.tail(5)
                for _, row in recent.iterrows():
                    ctx += f"- {row['document'][:300]}\n"
                ctx += "\n"
        except Exception:
            pass

    if req.include_code:
        try:
            query_text = " ".join([
                r["task_title"] for _, r in pending.iterrows()
            ]) if not pending.empty else "project overview"
            results = _search_table(code_table, query_text, limit=req.n_results)
            if pid:
                results = results[results["project_id"] == pid]
            if not results.empty:
                ctx += "### Fragmentos de Codigo Relevantes:\n"
                for _, row in results.iterrows():
                    ctx += f"// {row['file_path']}\n{row['document'][:400]}\n\n"
        except Exception:
            pass

    if req.include_documents:
        try:
            results = _search_table(doc_table, "project overview", limit=3)
            if pid:
                results = results[results["project_id"] == pid]
            if not results.empty:
                ctx += "### Documentos Relevantes:\n"
                for _, row in results.iterrows():
                    src = row.get("source_file", "unknown")
                    ctx += f"- [{row.get('doc_type', 'txt')}] {src}: {row['document'][:300]}\n"
                ctx += "\n"
        except Exception:
            pass

    return {
        "context": ctx.strip(),
        "has_tasks": req.include_tasks,
        "has_decisions": req.include_decisions,
    }


# ═══════════════════════════════════════════════════════════════════
#  Auto-Consolidation — Memory decay & task re-promotion
# ═══════════════════════════════════════════════════════════════════

# In-memory task access tracker for M_score
_task_access: dict[str, dict[str, Any]] = {}


def _bump_task_access(task_id: str) -> None:
    import time
    if task_id in _task_access:
        _task_access[task_id]["last_access"] = time.time()
        _task_access[task_id]["count"] += 1
    else:
        _task_access[task_id] = {"last_access": time.time(), "count": 1}


def _detect_stale_tasks(days_stale: int = 3) -> list[dict]:
    """Find tasks not updated in N days — candidates for re-promotion."""
    threshold = datetime.utcnow() - timedelta(days=days_stale)
    stale = []
    try:
        df = task_table.to_pandas()
        for _, row in df.iterrows():
            if row["task_status"] in ("cancelled",):
                continue
            updated = row.get("updated_at", "")
            if updated:
                try:
                    dt = datetime.fromisoformat(updated)
                    if dt < threshold and row["task_status"] != "completed":
                        stale.append({
                            "id": row["id"],
                            "title": row["task_title"],
                            "status": row["task_status"],
                            "last_updated": updated,
                        })
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return stale


@app.post("/consolidate")
async def consolidate_memory(req: ProjectInfoRequest):
    """Manual trigger for memory consolidation.

    Detects stale tasks (not updated in 3+ days) and re-promotes them
    by resetting their status to 'pending' with a reminder note.
    Also computes M_score decay on indexed content.
    """
    try:
        pid = validate_project_id(req.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    report: list[str] = []
    actions = 0

    stale = _detect_stale_tasks()
    if pid:
        stale = [t for t in stale if pid in t.get("id", "")]

    for task in stale:
        task_id = task["id"]
        _bump_task_access(task_id)
        now = datetime.utcnow().isoformat()
        doc = (
            f"title: {task['title']} | status: pending | "
            f"priority: high | context: [RE-PROMOTED] Stale for 3+ days"
        )
        vectors = _embed_documents([doc])
        _delete_by_id(task_table, task_id)
        task_table.add([{
            "id": task_id,
            "document": doc,
            "task_title": task["title"],
            "task_status": "pending",
            "task_priority": "high",
            "task_dependencies": "[]",
            "project_id": pid or "",
            "created_at": task.get("last_updated", now),
            "updated_at": now,
            "vector": vectors[0],
        }])
        report.append(f"Re-promoted: {task['title']}")
        actions += 1

    # Compute M_score decay for code chunks
    try:
        from memory.mscore import MemoryRelevanceManager
        mgr = MemoryRelevanceManager(lambda_days=30.0, w_freq=0.5)
        df = code_table.to_pandas()
        if pid:
            df = df[df["project_id"] == pid]
        scored = mgr.consolidate_scores([
            {"memory_id": r["id"], "similarity": 0.5}
            for _, r in df.iterrows()
        ])
        low_score = [s for s in scored if s["m_score"] < 0.3]
        report.append(f"M_score computed: {len(scored)} chunks, {len(low_score)} below threshold")
    except Exception as e:
        report.append(f"M_score computation skipped: {e}")

    return {
        "status": "consolidated",
        "stale_tasks_found": len(stale),
        "tasks_re_promoted": actions,
        "report": report,
    }


# ═══════════════════════════════════════════════════════════════════
#  Startup — Preload embedding model and start consolidation worker
# ═══════════════════════════════════════════════════════════════════

_CONSOLIDATION_INTERVAL = 3600  # seconds (1 hour)


def _start_consolidation_worker():
    """Background thread that periodically consolidates memories."""
    import threading

    def _worker():
        import time as _time
        print("[kinnycode] Consolidation worker started (interval: 1h)", file=sys.stderr)
        while True:
            try:
                _time.sleep(_CONSOLIDATION_INTERVAL)
                stale = _detect_stale_tasks()
                if stale:
                    print(
                        f"[kinnycode] Consolidation: found {len(stale)} stale tasks",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"[kinnycode] Consolidation error: {e}", file=sys.stderr)
                _time.sleep(60)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


@app.on_event("startup")
async def preload_embedding_model():
    """Preload the sentence-transformers model at startup."""
    print("[kinnycode] Preloading embedding model (all-MiniLM-L6-v2)...", file=sys.stderr)
    model = _get_embed_model()
    _ = model.encode(["warmup"], normalize_embeddings=True)
    print("[kinnycode] Embedding model ready.", file=sys.stderr)
    _start_consolidation_worker()

# ═══════════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("KINNYCODE_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8007)
