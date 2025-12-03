"""Research mode progress tracking."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Set

if TYPE_CHECKING:
    from ..tools.base import ToolResult

from ..config import CONFIG
from ..logging_utils import LogTag, format_progress, format_decision


@dataclass
class ResearchStats:
    """
    Tracks research mode progress through planning, execution, and synthesis phases.

    This class centralizes all research statistics tracking to ensure consistency
    across different tool execution paths (batch vs individual calls).
    """

    # Phase tracking
    has_plan: bool = False
    plan_text: str = ""
    synthesis_triggered: bool = False

    # Tool execution tracking
    tool_calls: int = 0
    searches: int = 0
    sources_fetched: int = 0

    # Data tracking
    unique_urls: Set[str] = field(default_factory=set)
    search_queries: List[str] = field(default_factory=list)

    # Execution path tracking (for debugging)
    batch_executions: int = 0
    individual_executions: int = 0

    # Private fields for logging
    _logger: logging.Logger = field(default=None, init=False, repr=False)
    _session_id: str = field(default="", init=False, repr=False)

    def __post_init__(self):
        """Initialize logger after dataclass initialization."""
        self._logger = logging.getLogger(__name__)

    def set_session(self, session_id: str) -> None:
        """Set session ID for logging context."""
        self._session_id = session_id

    def track_tool_result(
        self,
        tool_name: str,
        result: "ToolResult",
        arguments: Dict[str, Any],
        user_message: str = "",
        execution_path: str = "unknown"
    ) -> None:
        """
        Centralized method to track any tool execution.

        This ensures consistent tracking regardless of execution path
        (batch vs individual tool calls).

        Args:
            tool_name: Name of the tool that was executed
            result: Tool execution result
            arguments: Arguments passed to the tool
            user_message: User's message (used as fallback for queries)
            execution_path: Which code path executed this ("batch" or "individual")
        """
        self.tool_calls += 1

        # Track execution path
        if execution_path == "batch":
            self.batch_executions += 1
        elif execution_path == "individual":
            self.individual_executions += 1

        if tool_name == "web_search":
            self.searches += 1
            query = arguments.get("query", user_message)
            self.search_queries.append(str(query))

            # LLM-readable logging (compact, only in debug mode)
            if CONFIG.debug.research_mode:
                # Format: [R:SRCH] #2 (batch, q=...)
                msg = format_progress(
                    LogTag.RESEARCH_SEARCH,
                    self.searches,
                    total=3,  # Typical research has ~3 searches
                    p=execution_path[:1],  # b or i
                    q=query[:30]  # First 30 chars
                )
                self._logger.debug(msg, extra={"session_id": self._session_id})

        elif tool_name == "web_access":
            if result.metadata:
                url = result.metadata.get("url")
                if url:
                    before_count = len(self.unique_urls)
                    self.unique_urls.add(url)
                    self.sources_fetched += 1

                    # Log NEW unique URLs (compact LLM-readable format)
                    if len(self.unique_urls) > before_count:
                        current = len(self.unique_urls)
                        # Format: [R:URL] #3/3 ✓ (b) or [R:URL] #1/3 (i)
                        msg = format_progress(
                            LogTag.RESEARCH_URL,
                            current,
                            total=3,  # Need 3+ for synthesis
                            p=execution_path[:1]  # b or i
                        )

                        # Always log URLs at INFO (milestone), but keep it compact
                        self._logger.info(msg, extra={"session_id": self._session_id})

    def should_trigger_synthesis(self) -> bool:
        """
        Check if synthesis phase should be triggered.

        Synthesis requires:
        - Research plan exists (has_plan=True)
        - At least 3 unique URLs have been fetched
        - Synthesis hasn't been triggered yet
        """
        should_trigger = (
            self.has_plan
            and len(self.unique_urls) >= 3
            and not self.synthesis_triggered
        )

        # Log decision (compact format, only when False or in debug mode)
        if CONFIG.debug.research_mode or not should_trigger:
            # Format: [D:] synth=Y (p=Y,u=3) or [D:] synth=N (p=N,u=2)
            msg = format_decision(
                "synth",
                should_trigger,
                p="Y" if self.has_plan else "N",
                u=f"{len(self.unique_urls)}",
                t="Y" if self.synthesis_triggered else "N"
            )
            log_level = logging.DEBUG if should_trigger else logging.INFO
            self._logger.log(log_level, msg, extra={"session_id": self._session_id})

        return should_trigger

    def get_phase(self) -> str:
        """
        Return current research phase.

        Returns:
            "planning" | "execution" | "synthesis"
        """
        if not self.has_plan:
            return "planning"
        elif not self.synthesis_triggered:
            return "execution"
        else:
            return "synthesis"

    def get_sources_count(self) -> int:
        """Return count of unique URLs tracked."""
        return len(self.unique_urls)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dict for logging/serialization.

        Returns:
            Dictionary representation of all stats
        """
        return {
            "has_plan": self.has_plan,
            "synthesis_triggered": self.synthesis_triggered,
            "tool_calls": self.tool_calls,
            "searches": self.searches,
            "sources_fetched": self.sources_fetched,
            "unique_urls_count": len(self.unique_urls),
            "unique_urls": list(self.unique_urls),
            "search_queries": self.search_queries,
            "phase": self.get_phase(),
            "batch_executions": self.batch_executions,
            "individual_executions": self.individual_executions
        }

    def __repr__(self) -> str:
        """Human-readable representation."""
        return (
            f"ResearchStats(phase={self.get_phase()}, "
            f"tool_calls={self.tool_calls}, "
            f"urls={len(self.unique_urls)}, "
            f"batch={self.batch_executions}, "
            f"individual={self.individual_executions})"
        )
