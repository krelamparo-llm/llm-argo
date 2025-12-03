"""Tests for ResearchStats tracking."""

import pytest
from argo_brain.assistant.research_tracker import ResearchStats
from argo_brain.tools.base import ToolResult


class TestResearchStatsTracking:
    """Test suite for research statistics tracking."""

    def test_initialization(self):
        """Verify ResearchStats initializes with correct defaults."""
        stats = ResearchStats()

        assert stats.has_plan is False
        assert stats.plan_text == ""
        assert stats.synthesis_triggered is False
        assert stats.tool_calls == 0
        assert stats.searches == 0
        assert stats.sources_fetched == 0
        assert len(stats.unique_urls) == 0
        assert len(stats.search_queries) == 0
        assert stats.batch_executions == 0
        assert stats.individual_executions == 0

    def test_track_web_search(self):
        """Verify web_search increments searches counter."""
        stats = ResearchStats()
        stats.set_session("test-session")

        result = ToolResult(
            tool_name="web_search",
            summary="Found 5 results",
            content="Search results...",
            metadata={}
        )

        stats.track_tool_result(
            tool_name="web_search",
            result=result,
            arguments={"query": "test query"},
            user_message="",
            execution_path="batch"
        )

        assert stats.tool_calls == 1
        assert stats.searches == 1
        assert "test query" in stats.search_queries
        assert stats.batch_executions == 1
        assert stats.individual_executions == 0

    def test_track_web_access_adds_unique_url(self):
        """Verify web_access adds unique URLs."""
        stats = ResearchStats()
        stats.set_session("test-session")

        result = ToolResult(
            tool_name="web_access",
            summary="Fetched page",
            content="Page content...",
            metadata={"url": "https://example.com"}
        )

        stats.track_tool_result(
            tool_name="web_access",
            result=result,
            arguments={},
            user_message="",
            execution_path="individual"
        )

        assert stats.tool_calls == 1
        assert len(stats.unique_urls) == 1
        assert "https://example.com" in stats.unique_urls
        assert stats.sources_fetched == 1
        assert stats.batch_executions == 0
        assert stats.individual_executions == 1

    def test_track_duplicate_url_does_not_increment_unique(self):
        """Verify duplicate URLs don't increment unique count."""
        stats = ResearchStats()
        stats.set_session("test-session")

        result = ToolResult(
            tool_name="web_access",
            summary="Fetched page",
            content="Page content...",
            metadata={"url": "https://example.com"}
        )

        # Track same URL twice
        stats.track_tool_result("web_access", result, {}, "", "batch")
        stats.track_tool_result("web_access", result, {}, "", "individual")

        assert stats.tool_calls == 2  # Both calls counted
        assert len(stats.unique_urls) == 1  # Only 1 unique URL
        assert stats.sources_fetched == 2  # Both fetches counted
        assert stats.batch_executions == 1
        assert stats.individual_executions == 1

    def test_track_multiple_unique_urls(self):
        """Verify multiple unique URLs are tracked separately."""
        stats = ResearchStats()
        stats.set_session("test-session")

        urls = [
            "https://example1.com",
            "https://example2.com",
            "https://example3.com"
        ]

        for i, url in enumerate(urls):
            result = ToolResult(
                tool_name="web_access",
                summary=f"Fetched page {i+1}",
                content="Content...",
                metadata={"url": url}
            )
            execution_path = "batch" if i % 2 == 0 else "individual"
            stats.track_tool_result("web_access", result, {}, "", execution_path)

        assert stats.tool_calls == 3
        assert len(stats.unique_urls) == 3
        assert all(url in stats.unique_urls for url in urls)
        assert stats.sources_fetched == 3
        assert stats.batch_executions == 2  # indices 0, 2
        assert stats.individual_executions == 1  # index 1

    def test_synthesis_trigger_conditions(self):
        """Verify synthesis triggers with plan + 3 URLs."""
        stats = ResearchStats()
        stats.set_session("test-session")
        stats.has_plan = True

        # Should NOT trigger with only 2 URLs
        for i in range(2):
            result = ToolResult(
                tool_name="web_access",
                summary="Fetched",
                content="...",
                metadata={"url": f"https://example{i}.com"}
            )
            stats.track_tool_result("web_access", result, {}, "", "batch")

        assert not stats.should_trigger_synthesis()
        assert len(stats.unique_urls) == 2

        # SHOULD trigger with 3rd URL
        result = ToolResult(
            tool_name="web_access",
            summary="Fetched",
            content="...",
            metadata={"url": "https://example3.com"}
        )
        stats.track_tool_result("web_access", result, {}, "", "batch")

        assert stats.should_trigger_synthesis()
        assert len(stats.unique_urls) == 3

    def test_synthesis_requires_plan(self):
        """Verify synthesis requires both plan AND URLs."""
        stats = ResearchStats()
        stats.set_session("test-session")

        # Add 3 URLs but no plan
        for i in range(3):
            result = ToolResult(
                tool_name="web_access",
                summary="Fetched",
                content="...",
                metadata={"url": f"https://example{i}.com"}
            )
            stats.track_tool_result("web_access", result, {}, "", "batch")

        assert len(stats.unique_urls) == 3
        assert not stats.should_trigger_synthesis()  # No plan yet

        # Add plan
        stats.has_plan = True
        assert stats.should_trigger_synthesis()  # Now should trigger

    def test_synthesis_does_not_retrigger(self):
        """Verify synthesis only triggers once."""
        stats = ResearchStats()
        stats.set_session("test-session")
        stats.has_plan = True

        # Add 3 URLs
        for i in range(3):
            result = ToolResult(
                tool_name="web_access",
                summary="Fetched",
                content="...",
                metadata={"url": f"https://example{i}.com"}
            )
            stats.track_tool_result("web_access", result, {}, "", "batch")

        assert stats.should_trigger_synthesis()

        # Mark as triggered
        stats.synthesis_triggered = True

        # Should NOT trigger again
        assert not stats.should_trigger_synthesis()

    def test_phase_progression(self):
        """Verify phase transitions."""
        stats = ResearchStats()

        assert stats.get_phase() == "planning"

        stats.has_plan = True
        assert stats.get_phase() == "execution"

        stats.synthesis_triggered = True
        assert stats.get_phase() == "synthesis"

    def test_to_dict_conversion(self):
        """Verify to_dict includes all fields."""
        stats = ResearchStats()
        stats.set_session("test-session")
        stats.has_plan = True
        stats.plan_text = "Research plan..."

        # Add some data
        stats.track_tool_result(
            "web_search",
            ToolResult("web_search", "Results", "..."),
            {"query": "test"},
            "",
            "batch"
        )
        stats.track_tool_result(
            "web_access",
            ToolResult("web_access", "Fetched", "...", metadata={"url": "https://example.com"}),
            {},
            "",
            "individual"
        )

        data = stats.to_dict()

        assert data["has_plan"] is True
        assert data["synthesis_triggered"] is False
        assert data["tool_calls"] == 2
        assert data["searches"] == 1
        assert data["sources_fetched"] == 1
        assert data["unique_urls_count"] == 1
        assert "https://example.com" in data["unique_urls"]
        assert "test" in data["search_queries"]
        assert data["phase"] == "execution"
        assert data["batch_executions"] == 1
        assert data["individual_executions"] == 1

    def test_web_access_without_metadata(self):
        """Verify web_access handles missing metadata gracefully."""
        stats = ResearchStats()
        stats.set_session("test-session")

        result = ToolResult(
            tool_name="web_access",
            summary="Error fetching",
            content="...",
            metadata=None  # No metadata
        )

        # Should not crash
        stats.track_tool_result("web_access", result, {}, "", "batch")

        assert stats.tool_calls == 1
        assert len(stats.unique_urls) == 0
        assert stats.sources_fetched == 0

    def test_web_access_with_empty_url(self):
        """Verify web_access handles empty URL gracefully."""
        stats = ResearchStats()
        stats.set_session("test-session")

        result = ToolResult(
            tool_name="web_access",
            summary="Error",
            content="...",
            metadata={"url": ""}  # Empty URL
        )

        # Should not add empty URL
        stats.track_tool_result("web_access", result, {}, "", "batch")

        assert stats.tool_calls == 1
        assert len(stats.unique_urls) == 0
        assert stats.sources_fetched == 0

    def test_execution_path_tracking(self):
        """Verify execution path counters work correctly."""
        stats = ResearchStats()
        stats.set_session("test-session")

        result = ToolResult("web_search", "Results", "...")

        # Track via different paths
        stats.track_tool_result("web_search", result, {"query": "q1"}, "", "batch")
        stats.track_tool_result("web_search", result, {"query": "q2"}, "", "batch")
        stats.track_tool_result("web_search", result, {"query": "q3"}, "", "individual")
        stats.track_tool_result("web_search", result, {"query": "q4"}, "", "individual")
        stats.track_tool_result("web_search", result, {"query": "q5"}, "", "individual")

        assert stats.tool_calls == 5
        assert stats.batch_executions == 2
        assert stats.individual_executions == 3

    def test_get_sources_count(self):
        """Verify get_sources_count returns correct value."""
        stats = ResearchStats()
        stats.set_session("test-session")

        assert stats.get_sources_count() == 0

        # Add URLs
        for i in range(5):
            result = ToolResult(
                "web_access",
                "Fetched",
                "...",
                metadata={"url": f"https://example{i}.com"}
            )
            stats.track_tool_result("web_access", result, {}, "", "batch")

        assert stats.get_sources_count() == 5

    def test_repr(self):
        """Verify __repr__ is informative."""
        stats = ResearchStats()
        stats.set_session("test-session")
        stats.has_plan = True

        # Add some data
        for i in range(2):
            result = ToolResult(
                "web_access",
                "Fetched",
                "...",
                metadata={"url": f"https://example{i}.com"}
            )
            stats.track_tool_result("web_access", result, {}, "", "batch" if i == 0 else "individual")

        repr_str = repr(stats)

        assert "ResearchStats" in repr_str
        assert "phase=execution" in repr_str
        assert "tool_calls=2" in repr_str
        assert "urls=2" in repr_str
        assert "batch=1" in repr_str
        assert "individual=1" in repr_str


class TestResearchStatsIntegration:
    """Integration tests for ResearchStats in realistic scenarios."""

    def test_typical_research_workflow(self):
        """Test a complete research workflow."""
        stats = ResearchStats()
        stats.set_session("integration-test")

        # Phase 1: Planning
        assert stats.get_phase() == "planning"
        stats.has_plan = True
        stats.plan_text = "Research plan for testing"

        # Phase 2: Execution - multiple searches
        assert stats.get_phase() == "execution"

        for i in range(3):
            search_result = ToolResult(
                "web_search",
                f"Found {i+1} results",
                "...",
                metadata={}
            )
            stats.track_tool_result(
                "web_search",
                search_result,
                {"query": f"query {i+1}"},
                "",
                "batch"
            )

        assert stats.searches == 3
        assert len(stats.search_queries) == 3

        # Phase 2: Execution - fetch sources
        for i in range(4):
            access_result = ToolResult(
                "web_access",
                f"Fetched source {i+1}",
                "Content...",
                metadata={"url": f"https://source{i+1}.com"}
            )
            execution_path = "batch" if i < 2 else "individual"
            stats.track_tool_result(
                "web_access",
                access_result,
                {},
                "",
                execution_path
            )

        assert len(stats.unique_urls) == 4
        assert stats.sources_fetched == 4
        assert stats.batch_executions == 2 + 3  # 2 web_access + 3 web_search
        assert stats.individual_executions == 2  # 2 web_access

        # Check synthesis trigger
        assert stats.should_trigger_synthesis()

        # Phase 3: Synthesis
        stats.synthesis_triggered = True
        assert stats.get_phase() == "synthesis"

        # Verify final state
        final_state = stats.to_dict()
        assert final_state["has_plan"] is True
        assert final_state["synthesis_triggered"] is True
        assert final_state["tool_calls"] == 7  # 3 searches + 4 accesses
        assert final_state["searches"] == 3
        assert final_state["unique_urls_count"] == 4
        assert final_state["phase"] == "synthesis"

    def test_mixed_execution_paths(self):
        """Test that both execution paths produce same tracking results."""
        stats_batch = ResearchStats()
        stats_batch.set_session("batch-test")
        stats_batch.has_plan = True

        stats_individual = ResearchStats()
        stats_individual.set_session("individual-test")
        stats_individual.has_plan = True

        # Track same URLs via different paths
        urls = [
            "https://example1.com",
            "https://example2.com",
            "https://example3.com"
        ]

        for url in urls:
            result = ToolResult(
                "web_access",
                "Fetched",
                "...",
                metadata={"url": url}
            )

            stats_batch.track_tool_result("web_access", result, {}, "", "batch")
            stats_individual.track_tool_result("web_access", result, {}, "", "individual")

        # Both should have same URL tracking
        assert len(stats_batch.unique_urls) == 3
        assert len(stats_individual.unique_urls) == 3
        assert stats_batch.unique_urls == stats_individual.unique_urls

        # Both should trigger synthesis
        assert stats_batch.should_trigger_synthesis()
        assert stats_individual.should_trigger_synthesis()

        # Execution path counters should differ
        assert stats_batch.batch_executions == 3
        assert stats_batch.individual_executions == 0
        assert stats_individual.batch_executions == 0
        assert stats_individual.individual_executions == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
