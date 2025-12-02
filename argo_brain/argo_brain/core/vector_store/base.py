"""Abstract VectorStore interfaces and shared dataclasses."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

Metadata = Dict[str, Any]


@dataclass
class Document:
    """Unified representation of a stored or retrieved vector chunk."""

    id: str
    text: str
    score: float
    metadata: Metadata = field(default_factory=dict)


class VectorStore(ABC):
    """Backend-agnostic interface for similarity search storage."""

    @abstractmethod
    def add(
        self,
        namespace: str,
        texts: List[str],
        embeddings: np.ndarray,
        metadatas: Optional[List[Metadata]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Insert or upsert documents into the namespace."""

    @abstractmethod
    def query(
        self,
        namespace: str,
        query_embedding: np.ndarray,
        k: int = 5,
        filters: Optional[Metadata] = None,
    ) -> List[Document]:
        """Return the top-k most similar documents."""

    @abstractmethod
    def delete(
        self,
        namespace: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Metadata] = None,
    ) -> int:
        """Delete documents matching the ids or filters and return count."""

    def get_by_id(
        self,
        namespace: str,
        doc_id: str,
    ) -> Optional["Document"]:
        """Retrieve a single document by its ID.

        Default implementation returns None. Subclasses should override
        for backends that support direct ID lookup.
        """
        return None
