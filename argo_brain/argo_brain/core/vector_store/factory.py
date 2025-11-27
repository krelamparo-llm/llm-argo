"""Factory helpers for constructing VectorStore instances."""

from __future__ import annotations

from typing import Optional

from ...config import AppConfig, CONFIG
from .base import VectorStore
from .chromadb_impl import ChromaVectorStore

_VECTOR_STORE: Optional[VectorStore] = None


def create_vector_store(config: AppConfig = CONFIG) -> VectorStore:
    """Instantiate (or reuse) the configured VectorStore backend."""

    global _VECTOR_STORE
    if _VECTOR_STORE is not None:
        return _VECTOR_STORE
    backend = config.vector_store.backend.lower()
    if backend == "chroma":
        _VECTOR_STORE = ChromaVectorStore(config.vector_store.path)
    else:
        raise ValueError(f"Unsupported vector store backend: {config.vector_store.backend}")
    return _VECTOR_STORE


__all__ = ["create_vector_store"]
