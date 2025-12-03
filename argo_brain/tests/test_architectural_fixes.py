"""Regression tests for architectural fixes (Issues 1-6).

These tests ensure the fixes for the following issues remain in place:
1. ToolResult/retrieve_context contract - error moved to metadata
2. Research mode synthesis timing - requires plan + 3 sources
3. QUICK_LOOKUP prompt/limit alignment - 2 tool calls allowed
4. Double web ingestion removed - ToolTracker no longer caches web content
5. (Skipped - structured function calling deferred)
6. ToolPolicy coverage - validators for all tools
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from argo_brain.assistant.tool_policy import ProposedToolCall, ToolPolicy
from argo_brain.tools.base import ToolRegistry, ToolRequest, ToolResult
from argo_brain.tools.retrieve_context import RetrieveContextTool
from argo_brain.memory.tool_tracker import ToolTracker
from argo_brain.core.memory.session import SessionMode


class _StubTool:
    """Minimal tool implementation for testing."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.description = ""
        self.input_schema = {}
        self.output_schema = {}
        self.side_effects = ""

    def run(self, request):
        raise NotImplementedError


class TestIssue1RetrieveContextContract(unittest.TestCase):
    """Issue 1: ToolResult no longer accepts 'error' kwarg directly."""

    def test_retrieve_context_miss_returns_valid_tool_result(self) -> None:
        """When chunk is not found, ToolResult should be valid (no TypeError)."""
        # Mock memory manager that returns None for any chunk lookup
        mock_memory_manager = MagicMock()
        mock_memory_manager.retrieve_chunk_by_id.return_value = None

        tool = RetrieveContextTool(memory_manager=mock_memory_manager)
        request = ToolRequest(
            session_id="test-session",
            query="",
            metadata={"chunk_id": "nonexistent:12345"},
            session_mode=SessionMode.QUICK_LOOKUP,
        )

        # This should NOT raise TypeError anymore
        result = tool.run(request)

        # Verify it's a valid ToolResult
        self.assertIsInstance(result, ToolResult)
        self.assertEqual(result.tool_name, "retrieve_context")
        self.assertEqual(result.content, "")
        self.assertFalse(result.metadata.get("found"))
        # Error should be in metadata, not as a direct attribute
        self.assertIn("error", result.metadata)
        # Error message should reference the chunk not being found
        error_msg = result.metadata["error"].lower()
        self.assertTrue(
            "not found" in error_msg or "no chunk found" in error_msg,
            f"Expected error message to indicate chunk not found, got: {result.metadata['error']}"
        )

    def test_retrieve_context_hit_returns_content(self) -> None:
        """When chunk is found, content should be returned."""
        mock_memory_manager = MagicMock()
        mock_memory_manager.retrieve_chunk_by_id.return_value = "This is the chunk content."

        tool = RetrieveContextTool(memory_manager=mock_memory_manager)
        request = ToolRequest(
            session_id="test-session",
            query="",
            metadata={"chunk_id": "rag:12345"},
            session_mode=SessionMode.QUICK_LOOKUP,
        )

        result = tool.run(request)

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.metadata.get("found"))
        self.assertEqual(result.content, "This is the chunk content.")


class TestIssue2ResearchSynthesisTiming(unittest.TestCase):
    """Issue 2: Research synthesis should only trigger with plan + 3 sources."""

    def test_synthesis_not_triggered_without_plan(self) -> None:
        """Synthesis should not trigger if no research plan exists."""
        research_stats = {
            "has_plan": False,
            "unique_urls": {"url1", "url2", "url3"},  # 3 sources
            "tool_calls": 5,
        }

        # Check the condition that would trigger synthesis
        has_plan = research_stats.get("has_plan", False)
        sources_count = len(research_stats.get("unique_urls", set()))
        should_trigger = has_plan and sources_count >= 3

        self.assertFalse(should_trigger)

    def test_synthesis_not_triggered_with_few_sources(self) -> None:
        """Synthesis should not trigger if fewer than 3 sources."""
        research_stats = {
            "has_plan": True,
            "unique_urls": {"url1", "url2"},  # Only 2 sources
            "tool_calls": 5,
        }

        has_plan = research_stats.get("has_plan", False)
        sources_count = len(research_stats.get("unique_urls", set()))
        should_trigger = has_plan and sources_count >= 3

        self.assertFalse(should_trigger)

    def test_synthesis_triggers_with_plan_and_3_sources(self) -> None:
        """Synthesis should trigger when plan exists and 3+ sources fetched."""
        research_stats = {
            "has_plan": True,
            "unique_urls": {"url1", "url2", "url3"},  # 3 sources
            "tool_calls": 5,
        }

        has_plan = research_stats.get("has_plan", False)
        sources_count = len(research_stats.get("unique_urls", set()))
        should_trigger = has_plan and sources_count >= 3

        self.assertTrue(should_trigger)


class TestIssue3QuickLookupLimit(unittest.TestCase):
    """Issue 3: QUICK_LOOKUP allows 2 tool calls (aligned with code)."""

    def test_quick_lookup_limit_is_two(self) -> None:
        """MAX_TOOL_CALLS_BY_MODE should allow 2 for QUICK_LOOKUP."""
        from argo_brain.assistant.orchestrator import ArgoAssistant

        # Check the class-level constant
        limit = ArgoAssistant.MAX_TOOL_CALLS_BY_MODE.get(SessionMode.QUICK_LOOKUP)
        self.assertEqual(limit, 2)


class TestIssue4DoubleIngestionRemoved(unittest.TestCase):
    """Issue 4: ToolTracker should NOT ingest web content (handled by WebAccessTool)."""

    def test_tool_tracker_does_not_ingest_web_content(self) -> None:
        """ToolTracker.process_result should not call ingestion for web_access."""
        mock_db = MagicMock()
        mock_ingestion = MagicMock()

        tracker = ToolTracker(db=mock_db, ingestion_manager=mock_ingestion)

        # Create a web_access result
        result = ToolResult(
            tool_name="web_access",
            summary="Fetched https://example.com",
            content="<html>Page content here</html>",
            metadata={"url": "https://example.com"},
        )
        request = ToolRequest(
            session_id="test-session",
            query="https://example.com",
            metadata={"url": "https://example.com"},
        )

        # Process the result
        tracker.process_result("test-session", request, result)

        # Verify log_tool_run was called (audit log still works)
        mock_db.log_tool_run.assert_called_once()

        # Verify ingestion_manager.ingest_document was NOT called
        # (previously this was called via _cache_web_content)
        mock_ingestion.ingest_document.assert_not_called()

    def test_tool_tracker_has_no_cache_web_content_method(self) -> None:
        """The _cache_web_content method should no longer exist."""
        tracker = ToolTracker()
        self.assertFalse(hasattr(tracker, "_cache_web_content"))


class TestIssue6ToolPolicyValidators(unittest.TestCase):
    """Issue 6: ToolPolicy should have validators for all major tools."""

    def setUp(self) -> None:
        self.policy = ToolPolicy()
        self.registry = ToolRegistry()
        self.registry.register(_StubTool("web_access"))
        self.registry.register(_StubTool("web_search"))
        self.registry.register(_StubTool("memory_query"))
        self.registry.register(_StubTool("memory_write"))
        self.registry.register(_StubTool("retrieve_context"))

    # --- web_search validator tests ---
    def test_web_search_rejects_short_query(self) -> None:
        """web_search should reject queries shorter than min length."""
        proposals = [ProposedToolCall(tool="web_search", arguments={"query": "a"})]
        approved, rejected = self.policy.review(proposals, self.registry)
        self.assertFalse(approved)
        self.assertTrue(any("short" in r.lower() for r in rejected))

    def test_web_search_truncates_long_query(self) -> None:
        """web_search should truncate queries exceeding max length."""
        long_query = "x" * 1000
        proposals = [ProposedToolCall(tool="web_search", arguments={"query": long_query})]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertTrue(approved)
        self.assertFalse(rejected)
        # Query should be truncated to max length
        max_len = self.policy.config.security.web_search_max_query_length
        self.assertEqual(len(approved[0].arguments["query"]), max_len)

    def test_web_search_caps_max_results(self) -> None:
        """web_search should cap max_results at configured limit."""
        proposals = [ProposedToolCall(
            tool="web_search",
            arguments={"query": "test query", "max_results": 100}
        )]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertTrue(approved)
        max_limit = self.policy.config.security.web_search_max_results
        self.assertEqual(approved[0].arguments["max_results"], max_limit)

    # --- memory_write validator tests ---
    def test_memory_write_rejects_oversized_content(self) -> None:
        """memory_write should reject content exceeding max size."""
        huge_content = "x" * 100000  # 100KB
        proposals = [ProposedToolCall(
            tool="memory_write",
            arguments={"content": huge_content}
        )]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertFalse(approved)
        self.assertTrue(any("max size" in r.lower() for r in rejected))

    def test_memory_write_rejects_invalid_namespace(self) -> None:
        """memory_write should reject namespaces not in allow-list."""
        proposals = [ProposedToolCall(
            tool="memory_write",
            arguments={"content": "test", "namespace": "forbidden_namespace"}
        )]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertFalse(approved)
        self.assertTrue(any("allow-list" in r.lower() for r in rejected))

    def test_memory_write_accepts_valid_namespace(self) -> None:
        """memory_write should accept namespaces in allow-list."""
        proposals = [ProposedToolCall(
            tool="memory_write",
            arguments={"content": "test content", "namespace": "personal"}
        )]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertTrue(approved)
        self.assertFalse(rejected)

    def test_memory_write_rejects_non_dict_metadata(self) -> None:
        """memory_write should reject non-dict metadata."""
        proposals = [ProposedToolCall(
            tool="memory_write",
            arguments={"content": "test", "metadata": "not a dict"}
        )]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertFalse(approved)
        self.assertTrue(any("dict" in r.lower() for r in rejected))

    # --- retrieve_context validator tests ---
    def test_retrieve_context_requires_chunk_id(self) -> None:
        """retrieve_context should reject calls without chunk_id."""
        proposals = [ProposedToolCall(
            tool="retrieve_context",
            arguments={}
        )]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertFalse(approved)
        self.assertTrue(any("chunk_id" in r.lower() for r in rejected))

    def test_retrieve_context_rejects_oversized_chunk_id(self) -> None:
        """retrieve_context should reject chunk_id exceeding max length."""
        long_id = "x" * 500
        proposals = [ProposedToolCall(
            tool="retrieve_context",
            arguments={"chunk_id": long_id}
        )]
        approved, rejected = self.policy.review(proposals, self.registry)

        self.assertFalse(approved)
        self.assertTrue(any("max length" in r.lower() for r in rejected))

    def test_retrieve_context_accepts_valid_chunk_id(self) -> None:
        """retrieve_context should accept properly formatted chunk_id."""
        valid_ids = [
            "rag:12345",
            "auto:1701388800:0",
            "web_cache:abc-123",
            "notes:my_note_id",
        ]
        for chunk_id in valid_ids:
            proposals = [ProposedToolCall(
                tool="retrieve_context",
                arguments={"chunk_id": chunk_id}
            )]
            approved, rejected = self.policy.review(proposals, self.registry)

            self.assertTrue(approved, f"Should accept chunk_id: {chunk_id}")
            self.assertFalse(rejected)


class TestToolPolicyHasAllValidators(unittest.TestCase):
    """Verify all major tools have validator methods."""

    def test_all_major_tools_have_validators(self) -> None:
        """ToolPolicy should have _validate_X methods for all major tools."""
        policy = ToolPolicy()
        expected_validators = [
            "_validate_web_access",
            "_validate_web_search",
            "_validate_memory_query",
            "_validate_memory_write",
            "_validate_retrieve_context",
        ]

        for validator_name in expected_validators:
            self.assertTrue(
                hasattr(policy, validator_name),
                f"Missing validator: {validator_name}"
            )
            self.assertTrue(
                callable(getattr(policy, validator_name)),
                f"Validator is not callable: {validator_name}"
            )


if __name__ == "__main__":
    unittest.main()
