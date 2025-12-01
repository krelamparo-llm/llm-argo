"""Tests for the ToolPolicy plan validator."""

from __future__ import annotations

import unittest

from argo_brain.assistant.tool_policy import ProposedToolCall, ToolPolicy
from argo_brain.tools.base import ToolRegistry


class _StubTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = ""
        self.input_schema = {}
        self.output_schema = {}
        self.side_effects = ""

    def run(self, request):  # pragma: no cover - not invoked in tests
        raise NotImplementedError


class ToolPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ToolPolicy()
        self.registry = ToolRegistry()
        self.registry.register(_StubTool("web_access"))
        self.registry.register(_StubTool("memory_query"))

    def test_rejects_disallowed_web_scheme(self) -> None:
        proposals = [ProposedToolCall(tool="web_access", arguments={"url": "ftp://example.com"})]
        approved, rejected = self.policy.review(proposals, self.registry)
        self.assertFalse(approved)
        self.assertTrue(any("scheme" in reason.lower() for reason in rejected))

    def test_clamps_memory_query_top_k(self) -> None:
        proposals = [ProposedToolCall(tool="memory_query", arguments={"top_k": 99, "query": "foo"})]
        approved, rejected = self.policy.review(proposals, self.registry)
        self.assertFalse(rejected)
        self.assertEqual(approved[0].arguments["top_k"], self.policy.config.security.context_max_chunks)

    def test_unknown_tool_rejected(self) -> None:
        proposals = [ProposedToolCall(tool="nonexistent", arguments={})]
        approved, rejected = self.policy.review(proposals, self.registry)
        self.assertFalse(approved)
        self.assertTrue(rejected)


if __name__ == "__main__":
    unittest.main()
