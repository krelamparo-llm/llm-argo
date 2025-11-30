"""Integration test ensuring ingestion and retrieval share the same namespace."""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

import importlib
import numpy as np

from argo_brain.config import CONFIG
from argo_brain.core.memory.document import SourceDocument
from argo_brain.core.memory.ingestion import IngestionManager
from argo_brain.core.memory.session import SessionMode
from argo_brain.core.vector_store.base import Document, VectorStore
from argo_brain.core.vector_store import factory as factory_module


class FakeVectorStore(VectorStore):
    def __init__(self) -> None:
        self._data: Dict[str, List[Document]] = {}

    def add(
        self,
        namespace: str,
        texts: List[str],
        embeddings: np.ndarray,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        docs = self._data.setdefault(namespace, [])
        new_ids = ids or [f"{namespace}:{len(docs)+idx}" for idx in range(len(texts))]
        for idx, text in enumerate(texts):
            docs.append(
                Document(
                    id=new_ids[idx],
                    text=text,
                    score=0.0,
                    metadata=(metadatas or [{}])[idx] if metadatas else {},
                )
            )
        return new_ids

    def query(
        self,
        namespace: str,
        query_embedding: np.ndarray,
        k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        docs = list(self._data.get(namespace, []))
        if filters:
            docs = [doc for doc in docs if all(doc.metadata.get(key) == val for key, val in filters.items())]
        return docs[:k]

    def delete(
        self,
        namespace: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        return 0


class RagIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_store = FakeVectorStore()
        self.original_factory_store = factory_module._VECTOR_STORE
        factory_module._VECTOR_STORE = self.fake_store
        self.rag_module = importlib.reload(importlib.import_module("argo_brain.rag"))
        self.ingestion_manager = IngestionManager(
            vector_store=self.fake_store,
            embedder=lambda texts: [[float(len(text))] * 3 for text in texts],
        )
        self.original_store = self.rag_module._VECTOR_STORE
        self.original_embed_single = self.rag_module.embed_single
        self.rag_module._VECTOR_STORE = self.fake_store
        self.rag_module.embed_single = lambda _: [1.0, 1.0, 1.0]

    def tearDown(self) -> None:
        self.rag_module._VECTOR_STORE = self.original_store
        self.rag_module.embed_single = self.original_embed_single
        factory_module._VECTOR_STORE = self.original_factory_store

    def test_ingest_and_retrieve_same_namespace(self) -> None:
        unique_phrase = "orion-scout-probe"
        doc = SourceDocument(
            id="test:doc",
            source_type="web_article",
            raw_text=f"This document mentions {unique_phrase} as a key term.",
            cleaned_text=f"This document mentions {unique_phrase} as a key term.",
            url="https://example.com/test",
            metadata={},
        )
        self.ingestion_manager.ingest_document(
            doc,
            session_mode=SessionMode.INGEST,
            user_intent="explicit_save",
        )
        chunks = self.rag_module.retrieve_knowledge(unique_phrase, top_k=3)
        self.assertTrue(chunks, "Expected to retrieve at least one chunk")
        self.assertTrue(
            any(unique_phrase in chunk.text for chunk in chunks),
            "Retrieved chunks should contain the ingested text",
        )
        self.assertIn(
            CONFIG.collections.rag,
            self.fake_store._data,
            "Ingested data should land in the default RAG namespace",
        )


if __name__ == "__main__":
    unittest.main()
