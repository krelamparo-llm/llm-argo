"""Tests for MemoryQueryTool."""

from __future__ import annotations

import unittest

from argo_brain.core.vector_store.base import Document
from argo_brain.tools.base import ToolRequest
from argo_brain.tools.memory import MemoryQueryTool


class FakeMemoryManager:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.calls: list[dict] = []

    def query_memory(self, query: str, *, namespace: str | None = None, top_k: int = 5, filters=None):
        self.calls.append({"query": query, "namespace": namespace, "top_k": top_k, "filters": filters})
        return self.documents[:top_k]


class MemoryQueryToolTests(unittest.TestCase):
    def setUp(self) -> None:
        documents = [
            Document(id="1", text="Python tooling guide", score=0.05, metadata={"source_type": "web_article"}),
            Document(id="2", text="Research notes", score=0.1, metadata={"source_type": "notes"}),
        ]
        self.manager = FakeMemoryManager(documents)
        self.tool = MemoryQueryTool(
            memory_manager=self.manager,
            top_k=2,
            default_namespace="default_ns",
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
        self.assertTrue(self.manager.calls)
        last_call = self.manager.calls[-1]
        self.assertEqual(last_call["namespace"], "custom_ns")
        self.assertEqual(last_call["top_k"], 2)
        self.assertEqual(last_call["filters"]["source_type"], "web_article")
        self.assertEqual(last_call["filters"]["session_id"], "sess1")

    def test_defaults_use_configured_namespace(self) -> None:
        request = ToolRequest(session_id="sess2", query="notes overview", metadata={})
        result = self.tool.run(request)
        self.assertTrue(result.snippets)
        self.assertEqual(self.manager.calls[-1]["namespace"], "default_ns")
        self.assertEqual(result.metadata["namespace"], "default_ns")


if __name__ == "__main__":
    unittest.main()
