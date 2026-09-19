"""Embedding cache for avoiding re-computation of embeddings for the same text.

This module provides a simple in-memory cache that stores embeddings keyed by
the input text. Since embeddings are deterministic for a given provider and
model, caching avoids unnecessary API calls and improves performance.
"""

from __future__ import annotations

import threading

import numpy as np

from ai.providers.factory import get_embedder as get_default_embedder


class EmbeddingCache:
    """Thread-safe in-memory cache for embeddings.

    The cache stores embeddings as numpy arrays keyed by the input text.
    Hits return the cached embedding, misses compute and store the result.
    """

    def __init__(self) -> None:
        self._cache: dict[str, np.ndarray] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, text: str) -> np.ndarray | None:
        """Get embedding for text from cache.

        Args:
            text: The input text to get embedding for

        Returns:
            Cached embedding as numpy array, or None if not found
        """
        with self._lock:
            if text in self._cache:
                self._hits += 1
                return self._cache[text].copy()  # Return a copy to prevent mutation
            self._misses += 1
            return None

    def put(self, text: str, embedding: np.ndarray) -> None:
        """Store embedding for text in cache.

        Args:
            text: The input text
            embedding: The embedding vector to cache
        """
        with self._lock:
            self._cache[text] = embedding.copy()  # Store a copy to prevent mutation

    def clear(self) -> None:
        """Clear all cached embeddings."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with hits, misses, and size
        """
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache)
            }


# Global cache instance for use throughout the application
_embedding_cache = EmbeddingCache()


def get_embedding_cache() -> EmbeddingCache:
    """Get the global embedding cache instance.

    Returns:
        The global EmbeddingCache instance
    """
    return _embedding_cache


def cached_embed(text: str, embedder  = None) -> np.ndarray:
    """Get embedding for text, using cache to avoid duplicate computation.

    Args:
        text: The input text to embed
        embedder: The embedding provider to use if cache misses

    Returns:
        Embedding vector as numpy array
    """
    # Check cache first
    cached = get_embedding_cache().get(text)
    if cached is not None:
        return cached

    # Cache miss - compute embedding
    embedder = embedder or get_default_embedder()
    embedding = embedder.embed(text)
    # Store in cache for future use
    get_embedding_cache().put(text, embedding)

    return embedding