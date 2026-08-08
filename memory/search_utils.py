"""
Utilidades de búsqueda vectorial para el servidor de memoria.

Este módulo extrae funciones puras de búsqueda para facilitar las pruebas
unitarias sin tener que importar el servidor FastAPI completo.
"""

from __future__ import annotations

from typing import Any

# Embedding model (local, CPU-only — cross-platform compatible)
_EMBED_MODEL = None


def _get_embed_model():
    """Lazy-load the sentence-transformers embedding model (all-MiniLM-L6-v2)."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from sentence_transformers import SentenceTransformer

        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _EMBED_MODEL


def _embed_documents(docs: list[str]) -> list[list[float]]:
    """Embed a list of documents using the local sentence-transformers model."""
    model = _get_embed_model()
    return model.encode(docs, normalize_embeddings=True).tolist()


def _search_table(table, query_text: str, limit: int = 5, project_id: str = ""):
    """Search a LanceDB table with an optional project_id filter.

    Filtering happens at the vector database level instead of post-hoc,
    which prevents empty results when the global top-K vectors belong to
    other projects.
    """
    qv = _embed_documents([query_text])[0]
    query = table.search(qv)
    if project_id:
        query = query.where(f"project_id = '{project_id}'")
    return query.limit(limit).to_pandas()
