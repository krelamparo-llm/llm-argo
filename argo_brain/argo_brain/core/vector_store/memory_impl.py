"""Simple in-memory VectorStore used for testing or sandboxed environments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .base import Document, Metadata, VectorStore


@dataclass
class _StoredDoc:
    id: str
    text: str
    embedding: np.ndarray
    metadata: Metadata


class InMemoryVectorStore(VectorStore):
    """A minimal VectorStore implementation that keeps data in process memory."""

    def __init__(self) -> None:
        self._namespaces: Dict[str, List[_StoredDoc]] = {}

    def add(
        self,
        namespace: str,
        texts: List[str],
        embeddings: np.ndarray,
        metadatas: Optional[List[Metadata]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        docs = self._namespaces.setdefault(namespace, [])
        generated_ids: List[str] = []
        for idx, text in enumerate(texts):
            doc_id = ids[idx] if ids else f"{namespace}:{len(docs)+idx}"
            meta = (metadatas[idx] if metadatas else {}) or {}
            vector = np.array(embeddings[idx], dtype=float)
            docs.append(_StoredDoc(id=doc_id, text=text, embedding=vector, metadata=meta))
            generated_ids.append(doc_id)
        return generated_ids

    def query(
        self,
        namespace: str,
        query_embedding: np.ndarray,
        k: int = 5,
        filters: Optional[Metadata] = None,
    ) -> List[Document]:
        docs = list(self._namespaces.get(namespace, []))
        results: List[Document] = []
        for stored in docs:
            if filters and not self._matches_filters(stored.metadata, filters):
                continue
            similarity = self._similarity(stored.embedding, query_embedding)
            results.append(
                Document(
                    id=stored.id,
                    text=stored.text,
                    score=similarity,
                    metadata=stored.metadata,
                )
            )
        results.sort(key=lambda doc: doc.score, reverse=True)
        return results[:k]

    def delete(
        self,
        namespace: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Metadata] = None,
    ) -> int:
        docs = self._namespaces.get(namespace, [])
        if not docs:
            return 0
        original_len = len(docs)
        if ids:
            docs[:] = [doc for doc in docs if doc.id not in ids]
        elif filters:
            docs[:] = [doc for doc in docs if not self._matches_filters(doc.metadata, filters)]
        else:
            self._namespaces[namespace] = []
        return original_len - len(self._namespaces.get(namespace, []))

    def _similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denom)

    def _matches_filters(self, metadata: Metadata, filters: Metadata) -> bool:
        for key, value in filters.items():
            if isinstance(value, dict):
                # support simple $gt comparisons used in codebase
                if "$gt" in value:
                    if not float(metadata.get(key, 0)) > float(value["$gt"]):
                        return False
                continue
            if metadata.get(key) != value:
                return False
        return True


__all__ = ["InMemoryVectorStore"]
