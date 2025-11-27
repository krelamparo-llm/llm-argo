"""Chroma backend for the VectorStore abstraction."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from chromadb import PersistentClient
from chromadb.api.models.Collection import Collection

from .base import Document, Metadata, VectorStore


class ChromaVectorStore(VectorStore):
    """Concrete VectorStore implementation backed by ChromaDB."""

    def __init__(self, path: Path) -> None:
        self._client = PersistentClient(path=str(path))
        self._collections: Dict[str, Collection] = {}

    def _get_collection(self, namespace: str) -> Collection:
        if namespace not in self._collections:
            self._collections[namespace] = self._client.get_or_create_collection(name=namespace)
        return self._collections[namespace]

    def add(
        self,
        namespace: str,
        texts: List[str],
        embeddings: np.ndarray,
        metadatas: Optional[List[Metadata]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        if embeddings.size == 0 or not texts:
            return []
        if embeddings.shape[0] != len(texts):
            raise ValueError("Embeddings count must match number of texts")
        collection = self._get_collection(namespace)
        doc_ids = ids or [f"{namespace}:{idx}" for idx in range(len(texts))]
        payload_metadatas = metadatas or [{} for _ in texts]
        collection.upsert(
            ids=doc_ids,
            documents=texts,
            embeddings=embeddings.tolist(),
            metadatas=payload_metadatas,
        )
        return doc_ids

    def query(
        self,
        namespace: str,
        query_embedding: np.ndarray,
        k: int = 5,
        filters: Optional[Metadata] = None,
    ) -> List[Document]:
        collection = self._get_collection(namespace)
        response = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k,
            where=filters,
        )
        documents = response.get("documents", [[]])[0] or []
        metadata = response.get("metadatas", [[]])[0] or []
        ids = response.get("ids", [[]])[0] or []
        distances = response.get("distances", [[]])[0] or []
        results: List[Document] = []
        for doc, meta, doc_id, distance in zip(documents, metadata, ids, distances):
            results.append(
                Document(
                    id=doc_id,
                    text=doc or "",
                    score=float(distance) if distance is not None else 0.0,
                    metadata=meta or {},
                )
            )
        return results

    def delete(
        self,
        namespace: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Metadata] = None,
    ) -> int:
        collection = self._get_collection(namespace)
        # chromadb returns None for delete; we approximate count via ids when available.
        collection.delete(ids=ids, where=filters)
        if ids is not None:
            return len(ids)
        return 0
