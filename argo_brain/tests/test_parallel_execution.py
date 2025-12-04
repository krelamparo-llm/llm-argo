"""Tests for parallel tool execution in the orchestrator."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

# Ensure project root is on path for direct module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from argo_brain.assistant.orchestrator import ArgoAssistant, SessionMode
from argo_brain.assistant.tool_policy import ProposedToolCall
from argo_brain.log_setup import setup_logging
from argo_brain.tools.base import ToolRegistry, ToolResult


class _DummyTracker:
    """Minimal tracker to avoid hitting the real database."""

    def __init__(self) -> None:
        self.calls = []

    def process_result(self, session_id, request, result) -> None:  # pragma: no cover - trivial
        self.calls.append((session_id, request, result))


class _SleepTool:
    """Tool that sleeps to simulate work and exposes its thread id."""

    name = "sleep_tool"
    description = "Test tool that sleeps for a short duration."
    input_schema = {"type": "object"}
    output_schema = {"type": "object"}
    side_effects = "none"

    def __init__(self, delay: float = 0.2) -> None:
        self.delay = delay

    def run(self, request) -> ToolResult:
        time.sleep(self.delay)
        return ToolResult(
            tool_name=self.name,
            summary=f"slept {self.delay}s for {request.query}",
            content="",
            metadata={"thread": threading.get_ident(), "delay": self.delay, "query": request.query},
        )


def test_execute_tools_parallel_runs_concurrently():
    """_execute_tools_parallel should run multiple tools at the same time."""

    registry = ToolRegistry()
    sleep_tool = _SleepTool(delay=0.2)
    registry.register(sleep_tool)
    tracker = _DummyTracker()

    # Initialize logging once to satisfy ArgoAssistant startup warning.
    setup_logging()

    assistant = ArgoAssistant(
        tool_registry=registry,
        tool_tracker=tracker,
        tools=[],  # Skip default tool registration; we only need our dummy tool.
    )

    proposals = [
        ProposedToolCall(tool="sleep_tool", arguments={"query": "first"}),
        ProposedToolCall(tool="sleep_tool", arguments={"query": "second"}),
    ]

    start = time.monotonic()
    results = assistant._execute_tools_parallel(
        proposals,
        session_id="test_session",
        user_message="run in parallel",
        active_mode=SessionMode.RESEARCH,
    )
    duration = time.monotonic() - start

    assert len(results) == 2
    assert len(tracker.calls) == 2  # Both tool runs were processed

    # Results should stay aligned with proposals
    assert [r.metadata["query"] for r in results] == ["first", "second"]

    # Each run should have happened on (at least) two worker threads.
    thread_ids = {r.metadata["thread"] for r in results}
    assert len(thread_ids) >= 2

    # Parallel execution should be noticeably faster than sequential (2 * delay).
    assert duration < sleep_tool.delay * 1.5, f"Parallel run took too long: {duration:.3f}s"
