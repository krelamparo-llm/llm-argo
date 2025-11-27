"""Unit tests for the ingestion manager."""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

import numpy as np

from argo_brain.config import CONFIG
from argo_brain.core.memory.document import SourceDocument
from argo_brain.core.memory.ingestion import IngestionManager
from argo_brain.core.memory.session import SessionMode
from argo_brain.core.vector_store.base import Document, VectorStore


class FakeVectorStore(VectorStore):
    def __init__(self) -> None:
        self.add_calls: List[Dict[str, Any]] = []

    def add(
        self,
        namespace: str,
        texts: List[str],
        embeddings: np.ndarray,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        self.add_calls.append({"namespace": namespace, "texts": list(texts), "metadatas": metadatas or []})
        return ids or []

    def query(
        self,
        namespace: str,
        query_embedding: np.ndarray,
        k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        return []

    def delete(
        self,
        namespace: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        return 0


class FakeLLM:
    def chat(self, messages, temperature: float = 0.2, max_tokens: int = 256) -> str:  # noqa: D401 - simple fake
        return "synthetic summary"


def fake_embedder(texts: List[str]) -> List[List[float]]:
    return [[1.0] * 3 for _ in texts]


class IngestionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeVectorStore()
        self.manager = IngestionManager(
            vector_store=self.store,
            llm_client=FakeLLM(),
            embedder=fake_embedder,
            chunk_size=100,
            chunk_overlap=10,
        )

    def test_ephemeral_policy_uses_web_cache_namespace(self) -> None:
        doc = SourceDocument(
            id="web:123",
            source_type="live_web",
            raw_text="Hello world" * 200,
            cleaned_text="Hello world" * 200,
            url="https://example.com",
            metadata={},
        )
        self.manager.ingest_document(doc, session_mode=SessionMode.QUICK_LOOKUP)
        self.assertTrue(self.store.add_calls)
        namespaces = {call["namespace"] for call in self.store.add_calls}
        self.assertIn(CONFIG.collections.web_cache, namespaces)

    def test_full_ingest_mode_writes_chunks_and_summary(self) -> None:
        doc = SourceDocument(
            id="doc:456",
            source_type="web_article",
            raw_text="Data science " * 400,
            cleaned_text="Data science " * 400,
            url="https://example.com/data",
            metadata={},
        )
        self.manager.ingest_document(doc, session_mode=SessionMode.INGEST)
        namespaces = [call["namespace"] for call in self.store.add_calls]
        self.assertIn(CONFIG.collections.web_articles, namespaces)
        self.assertIn(CONFIG.collections.notes, namespaces)


if __name__ == "__main__":
    unittest.main()
