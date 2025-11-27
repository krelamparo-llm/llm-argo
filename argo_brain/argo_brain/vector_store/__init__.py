"""Vector store factory and exports."""

from __future__ import annotations

from ..core.vector_store.base import Document, VectorStore
from ..core.vector_store.factory import create_vector_store


def get_vector_store() -> VectorStore:
    """Return a singleton vector store instance configured for Argo."""

    return create_vector_store()


__all__ = ["VectorStore", "Document", "get_vector_store"]
