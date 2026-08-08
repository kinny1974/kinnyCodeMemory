"""
EmbeddingCache — Cache for sentence-transformers embeddings.

This module provides a TTL-based cache for embedding vectors to avoid
recomputing embeddings for the same text content.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any


class EmbeddingCache:
    """TTL-based cache for embedding vectors.
    
    This cache stores embedding vectors keyed by the SHA-256 hash of the
    input text. Entries expire after the configured TTL (time-to-live).
    
    Attributes:
        ttl: Time-to-live in seconds for cache entries.
        max_size: Maximum number of entries in the cache.
    """

    def __init__(self, ttl: int = 3600, max_size: int = 10000):
        """Initialize EmbeddingCache.
        
        Args:
            ttl: Time-to-live in seconds. Default is 3600 (1 hour).
            max_size: Maximum cache size. Default is 10000 entries.
        """
        self.ttl = ttl
        self.max_size = max_size
        self._cache: dict[str, dict[str, Any]] = {}
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _compute_key(self, text: str) -> str:
        """Compute cache key from text content.
        
        Args:
            text: Input text to hash.
            
        Returns:
            SHA-256 hex digest of the text.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> list[float] | None:
        """Retrieve cached embedding for text.
        
        Args:
            text: Input text to look up.
            
        Returns:
            Cached embedding vector if found and not expired, None otherwise.
        """
        key = self._compute_key(text)
        
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] < self.ttl:
                self._stats["hits"] += 1
                return entry["embedding"]
            else:
                # Entry expired
                del self._cache[key]
        
        self._stats["misses"] += 1
        return None

    def set(self, text: str, embedding: list[float]) -> None:
        """Store embedding in cache.
        
        Args:
            text: Input text (used as key).
            embedding: Embedding vector to cache.
        """
        key = self._compute_key(text)
        
        # Evict oldest entries if at capacity
        if len(self._cache) >= self.max_size:
            self._evict_oldest()
        
        self._cache[key] = {
            "embedding": embedding,
            "timestamp": time.time(),
        }

    def get_batch(self, texts: list[str]) -> tuple[list[list[float] | None], list[int]]:
        """Retrieve cached embeddings for a batch of texts.
        
        Args:
            texts: List of input texts to look up.
            
        Returns:
            Tuple of (results, indices) where:
                - results: List of embeddings (None for cache misses)
                - indices: List of indices for cache misses
        """
        results = []
        miss_indices = []
        
        for i, text in enumerate(texts):
            cached = self.get(text)
            if cached is not None:
                results.append(cached)
            else:
                results.append(None)
                miss_indices.append(i)
        
        return results, miss_indices

    def set_batch(self, texts: list[str], embeddings: list[list[float]]) -> None:
        """Store multiple embeddings in cache.
        
        Args:
            texts: List of input texts.
            embeddings: List of embedding vectors.
        """
        for text, embedding in zip(texts, embeddings):
            self.set(text, embedding)

    def _evict_oldest(self) -> None:
        """Evict the oldest cache entries."""
        if not self._cache:
            return
        
        # Sort by timestamp and remove oldest 10%
        sorted_keys = sorted(
            self._cache.keys(),
            key=lambda k: self._cache[k]["timestamp"]
        )
        evict_count = max(1, len(sorted_keys) // 10)
        
        for key in sorted_keys[:evict_count]:
            del self._cache[key]
            self._stats["evictions"] += 1

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def get_stats(self) -> dict[str, int]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats:
                - size: Current number of entries
                - hits: Total cache hits
                - misses: Total cache misses
                - evictions: Total evictions
                - hit_rate: Hit rate as percentage
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (
            (self._stats["hits"] / total_requests * 100)
            if total_requests > 0
            else 0.0
        )
        
        return {
            "size": len(self._cache),
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "hit_rate": round(hit_rate, 2),
        }

    def cleanup_expired(self) -> int:
        """Remove all expired entries from cache.
        
        Returns:
            Number of entries removed.
        """
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now - entry["timestamp"] >= self.ttl
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        return len(expired_keys)
