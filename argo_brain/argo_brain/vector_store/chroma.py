"""Compatibility wrapper for the relocated ChromaVectorStore."""

from __future__ import annotations

from ..core.vector_store.chromadb_impl import ChromaVectorStore

__all__ = ["ChromaVectorStore"]
