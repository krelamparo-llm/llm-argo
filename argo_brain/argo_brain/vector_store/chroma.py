"""Chroma-based vector store implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from chromadb import PersistentClient
from chromadb.api.models.Collection import Collection

from .base import QueryResult, VectorStore


class ChromaVectorStore(VectorStore):
    """Vector store backed by a Chroma persistent client."""

    def __init__(self, path: Path) -> None:
        self._client = PersistentClient(path=str(path))
        self._collections: Dict[str, Collection] = {}

    def _get_collection(self, name: str) -> Collection:
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(name=name)
        return self._collections[name]

    def add(
        self,
        *,
        collection: str,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        coll = self._get_collection(collection)
        coll.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def query(
        self,
        *,
        collection: str,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        coll = self._get_collection(collection)
        response = coll.query(
            query_texts=query_texts,
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=filters,
        )
        documents = response.get("documents", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        ids = response.get("ids", [[]])[0]
        distances = response.get("distances", [[]])[0]
        return QueryResult(
            documents=list(documents),
            metadatas=[meta or {} for meta in metadatas],
            ids=list(ids),
            distances=list(distances),
        )
