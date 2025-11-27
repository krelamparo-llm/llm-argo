"""Vector store abstraction for Argo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class QueryResult:
    """Normalized vector store query response."""

    documents: List[str]
    metadatas: List[Dict[str, Any]]
    ids: List[str]
    distances: List[float]


class VectorStore(Protocol):
    """Interface implemented by vector store backends."""

    def add(
        self,
        *,
        collection: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Add or upsert documents into a named collection."""

    def query(
        self,
        *,
        collection: str,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """Query a collection and return matching documents."""
