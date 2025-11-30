"""Tests for MemoryQueryTool."""

from __future__ import annotations

import unittest

from argo_brain.core.vector_store.base import Document, VectorStore
from argo_brain.tools.base import ToolRequest
from argo_brain.tools.memory import MemoryQueryTool


class FakeVectorStore(VectorStore):
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.last_query: dict | None = None

    def add(self, namespace, texts, embeddings, metadatas=None, ids=None):
        raise NotImplementedError

    def query(self, namespace, query_embedding, k=5, filters=None):
        self.last_query = {
            "namespace": namespace,
            "k": k,
            "filters": filters,
        }
        return list(self.documents)

    def delete(self, namespace, ids=None, filters=None):
        return 0


class MemoryQueryToolTests(unittest.TestCase):
    def setUp(self) -> None:
        documents = [
            Document(id="1", text="Python tooling guide", score=0.05, metadata={"source_type": "web_article"}),
            Document(id="2", text="Research notes", score=0.1, metadata={"source_type": "notes"}),
        ]
        self.store = FakeVectorStore(documents)
        self.tool = MemoryQueryTool(
            vector_store=self.store,
            top_k=2,
            default_namespace="default_ns",
            embed_fn=lambda _: [0.1, 0.2, 0.3],
        )

    def test_namespace_and_filters_passed_to_vector_store(self) -> None:
        request = ToolRequest(
            session_id="sess1",
            query="python tools",
            metadata={
                "namespace": "custom_ns",
                "source_type": "web_article",
                "filters": {"session_id": "sess1"},
            },
        )
        result = self.tool.run(request)
        self.assertIn("custom_ns", result.summary)
        self.assertIsNotNone(self.store.last_query)
        self.assertEqual(self.store.last_query["namespace"], "custom_ns")
        self.assertEqual(self.store.last_query["k"], 2)
        self.assertEqual(self.store.last_query["filters"]["source_type"], "web_article")
        self.assertEqual(self.store.last_query["filters"]["session_id"], "sess1")

    def test_defaults_use_configured_namespace(self) -> None:
        request = ToolRequest(session_id="sess2", query="notes overview", metadata={})
        result = self.tool.run(request)
        self.assertTrue(result.snippets)
        self.assertEqual(self.store.last_query["namespace"], "default_ns")
        self.assertEqual(result.metadata["namespace"], "default_ns")


if __name__ == "__main__":
    unittest.main()
