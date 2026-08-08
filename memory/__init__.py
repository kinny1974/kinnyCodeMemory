"""
KinnyCode — Memory System (public API)

Multi-layer memory: MemoryClient (HTTP), MemoryManager (L1-L4),
ConversationStore, ProjectRules, FileWatcher, HashCache,
IgnorePatterns, PollingChangeDetector, DedupLock, HashCalculator, IChangeDetector,
DocumentLoader — ingesta de documentos PDF, Markdown, TXT con chunking.
"""

from .change_detector import (
    DedupLock,
    HashCalculator,
    IChangeDetector,
    PollingChangeDetector,
)
from .client import MemoryClient
from .conversation_store import ConversationStore
from .file_watcher import FileWatcher, start_file_watcher
from .hash_cache import HashCache
from .ignore_patterns import IgnorePatterns
from .memory_manager import (
    EpisodicMemoryManager,
    MemoryChunk,
    MemoryManager,
    ProceduralMemoryManager,
    SemanticMemoryManager,
    WorkingMemory,
)
from .mscore import (
    MemoryRelevanceManager,
    calculate_m_score,
    decay_factor,
)
from .project_rules import ProjectRules, load_project_rules
from .document_loader import (
    DocumentChunker,
    DocumentIngestor,
    MarkdownLoader,
    PDFLoader,
    TextLoader,
    load_document,
    split_text as chunk_text,
)

__all__ = [
    "MemoryClient",
    "MemoryManager",
    "MemoryChunk",
    "WorkingMemory",
    "EpisodicMemoryManager",
    "SemanticMemoryManager",
    "ProceduralMemoryManager",
    "ConversationStore",
    "ProjectRules",
    "load_project_rules",
    "FileWatcher",
    "start_file_watcher",
    "HashCache",
    "IgnorePatterns",
    "DedupLock",
    "HashCalculator",
    "IChangeDetector",
    "PollingChangeDetector",
    "calculate_m_score",
    "decay_factor",
    "MemoryRelevanceManager",
    "DocumentChunker",
    "DocumentIngestor",
    "PDFLoader",
    "MarkdownLoader",
    "TextLoader",
    "load_document",
    "chunk_text",
]
