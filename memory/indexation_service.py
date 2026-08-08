"""
IndexationService — Consolidates duplicated indexing logic.

This service centralizes code chunking, embedding, and database insertion
across all indexation endpoints (index-file, index-project, index-file-paths,
index-document).
"""
from __future__ import annotations

import hashlib
from typing import Any

import lancedb
from lancedb.table import Table


class IndexationService:
    """Service for indexing code, documents, and other content into LanceDB.
    
    This service consolidates the duplicated indexing logic found across
    multiple endpoints in memory_server.py.
    
    Attributes:
        db: LanceDB connection instance.
        embed_func: Function to generate embeddings from text.
        split_func: Function to split text into chunks.
    """

    def __init__(
        self,
        db: lancedb.DBConnection,
        embed_func: callable,
        split_func: callable,
    ):
        """Initialize IndexationService.
        
        Args:
            db: LanceDB connection instance.
            embed_func: Function that takes a list of strings and returns
                       a list of embedding vectors.
            split_func: Function that takes (content, language) and returns
                       a list of text chunks.
        """
        self.db = db
        self.embed_func = embed_func
        self.split_func = split_func

    def compute_content_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content for deduplication.
        
        Args:
            content: Text content to hash.
            
        Returns:
            Hex-encoded SHA-256 hash string (64 characters).
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def index_code_chunks(
        self,
        table: Table,
        file_path: str,
        content: str,
        language: str,
        project_id: str = "",
        content_hash: str | None = None,
    ) -> dict[str, Any]:
        """Index code chunks into a LanceDB table.
        
        This method handles:
        1. Text splitting into chunks
        2. Embedding generation
        3. Deduplication (delete old chunks for same file_path)
        4. Batch insertion
        
        Args:
            table: LanceDB table to insert into.
            file_path: Path of the source file.
            content: Full source code content.
            language: Programming language.
            project_id: Project namespace identifier.
            content_hash: Optional pre-computed hash. If None, computed from content.
            
        Returns:
            Dictionary with indexing results:
                - chunks_indexed: Number of chunks inserted
                - content_hash: SHA-256 hash of the content
        """
        # Compute hash if not provided
        if content_hash is None:
            content_hash = self.compute_content_hash(content)

        # Split content into chunks
        chunks = self.split_func(content, language)
        
        if not chunks:
            return {"chunks_indexed": 0, "content_hash": content_hash}

        # Generate chunk IDs
        ids = [f"{file_path}_chunk_{i}" for i in range(len(chunks))]

        # Delete old chunks for this file (deduplication)
        self._delete_by_file_path(table, file_path, project_id)

        # Generate embeddings
        vectors = self.embed_func(chunks)

        # Prepare data for insertion
        data = [
            {
                "id": ids[i],
                "document": chunks[i],
                "file_path": file_path,
                "language": language,
                "content_hash": content_hash,
                "project_id": project_id,
                "vector": vectors[i],
            }
            for i in range(len(chunks))
        ]

        # Insert into table
        table.add(data)

        return {"chunks_indexed": len(chunks), "content_hash": content_hash}

    def index_document_chunks(
        self,
        table: Table,
        chunks: list[dict],
        project_id: str = "",
    ) -> dict[str, Any]:
        """Index document chunks into a LanceDB table.
        
        This method handles batch embedding and insertion for document chunks.
        
        Args:
            table: LanceDB table to insert into.
            chunks: List of chunk dictionaries with keys:
                    - id: Unique identifier
                    - document: Text content
                    - source_file: Source file path
                    - doc_type: Document type
                    - chunk_index: Index of chunk in document
                    - page_number: Page number (optional)
                    - content_hash: Content hash
            project_id: Project namespace identifier.
            
        Returns:
            Dictionary with indexing results:
                - chunks_indexed: Number of chunks inserted
        """
        if not chunks:
            return {"chunks_indexed": 0}

        # Extract text from chunks for embedding
        documents = [c["document"] for c in chunks]

        # Generate embeddings in batches
        BATCH_SIZE = 100
        total_indexed = 0

        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch_chunks = chunks[batch_start:batch_start + BATCH_SIZE]
            batch_docs = [c["document"] for c in batch_chunks]
            
            # Generate embeddings for this batch
            vectors = self.embed_func(batch_docs)

            # Prepare data for insertion
            data = [
                {
                    "id": batch_chunks[i]["id"],
                    "document": batch_chunks[i]["document"],
                    "source_file": batch_chunks[i]["source_file"],
                    "doc_type": batch_chunks[i]["doc_type"],
                    "chunk_index": batch_chunks[i]["chunk_index"],
                    "page_number": batch_chunks[i].get("page_number"),
                    "content_hash": batch_chunks[i]["content_hash"],
                    "project_id": project_id,
                    "vector": vectors[i],
                }
                for i in range(len(batch_chunks))
            ]

            # Insert batch
            table.add(data)
            total_indexed += len(batch_chunks)

        return {"chunks_indexed": total_indexed}

    def index_batch_files(
        self,
        table: Table,
        files: list[dict],
        project_id: str = "",
        clear_first: bool = False,
    ) -> dict[str, Any]:
        """Index multiple code files in batch.
        
        Args:
            table: LanceDB table to insert into.
            files: List of file dictionaries with keys:
                   - file_path: Path of the file
                   - content: File content
                   - language: Programming language
            project_id: Project namespace identifier.
            clear_first: If True, clear existing data for project first.
            
        Returns:
            Dictionary with indexing results:
                - files_indexed: Number of files processed
                - chunks_indexed: Total chunks inserted
        """
        if clear_first:
            self._delete_by_project_id(table, project_id)

        total_files = 0
        total_chunks = 0

        for fdata in files:
            file_path = fdata.get("file_path", "")
            content = fdata.get("content", "")
            language = fdata.get("language", "text")

            if not content.strip():
                continue

            result = self.index_code_chunks(
                table=table,
                file_path=file_path,
                content=content,
                language=language,
                project_id=project_id,
            )
            total_files += 1
            total_chunks += result["chunks_indexed"]

        return {
            "files_indexed": total_files,
            "chunks_indexed": total_chunks,
        }

    def _delete_by_file_path(
        self, table: Table, file_path: str, project_id: str = ""
    ) -> None:
        """Delete all rows matching a file_path.
        
        Args:
            table: LanceDB table.
            file_path: File path to match.
            project_id: Optional project_id filter.
        """
        try:
            try:
                df = table.search().where(f"file_path = '{file_path}'").limit(10000).to_pandas()
            except TypeError:
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

    def _delete_by_project_id(self, table: Table, project_id: str) -> None:
        """Delete all rows matching a project_id.
        
        Args:
            table: LanceDB table.
            project_id: Project ID to match.
        """
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
