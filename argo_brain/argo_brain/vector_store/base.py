"""Backwards-compatible shim for the new core.vector_store APIs."""

from __future__ import annotations

from ..core.vector_store.base import Document, VectorStore

__all__ = ["Document", "VectorStore"]
