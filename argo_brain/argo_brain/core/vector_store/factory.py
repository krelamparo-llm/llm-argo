"""Factory helpers for constructing VectorStore instances."""

from __future__ import annotations

import logging
from typing import Optional

from ...config import AppConfig, CONFIG
from .base import VectorStore
from .chromadb_impl import ChromaVectorStore
from .memory_impl import InMemoryVectorStore

_VECTOR_STORE: Optional[VectorStore] = None
_LOGGER = logging.getLogger("argo_brain.vector_store")


def create_vector_store(config: AppConfig = CONFIG) -> VectorStore:
    """Instantiate (or reuse) the configured VectorStore backend."""

    global _VECTOR_STORE
    if _VECTOR_STORE is not None:
        return _VECTOR_STORE
    backend = config.vector_store.backend.lower()
    if backend in {"memory", "stub", "inmemory"}:
        _VECTOR_STORE = InMemoryVectorStore()
        return _VECTOR_STORE
    if backend == "chroma":
        try:
            _VECTOR_STORE = ChromaVectorStore(config.vector_store.path)
            return _VECTOR_STORE
        except Exception as exc:  # noqa: BLE001 - fallback to in-memory store for tests
            _LOGGER.warning(
                "Failed to initialize Chroma backend, falling back to in-memory store: %s", exc
            )
            _VECTOR_STORE = InMemoryVectorStore()
            return _VECTOR_STORE
    raise ValueError(f"Unsupported vector store backend: {config.vector_store.backend}")


__all__ = ["create_vector_store"]
