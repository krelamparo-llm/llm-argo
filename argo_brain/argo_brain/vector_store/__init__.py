"""Vector store factory and exports."""

from __future__ import annotations

from typing import Optional

from ..config import CONFIG
from .base import QueryResult, VectorStore
from .chroma import ChromaVectorStore

_VECTOR_STORE: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Return a singleton vector store instance configured for Argo."""

    global _VECTOR_STORE
    if _VECTOR_STORE is not None:
        return _VECTOR_STORE

    backend = CONFIG.vector_store.backend.lower()
    if backend == "chroma":
        _VECTOR_STORE = ChromaVectorStore(CONFIG.vector_store.path)
    else:
        raise ValueError(f"Unsupported vector store backend: {CONFIG.vector_store.backend}")
    return _VECTOR_STORE


__all__ = ["VectorStore", "QueryResult", "get_vector_store"]
