"""Tool execution tracking."""

from __future__ import annotations

import logging
from typing import List, Optional

from ..core.memory.ingestion import IngestionManager
from ..tools.base import ToolRequest, ToolResult
from .db import MemoryDB, ToolRunRecord


class ToolTracker:
    """Logs and retrieves tool execution records."""

    def __init__(
        self,
        db: Optional[MemoryDB] = None,
        ingestion_manager: Optional[IngestionManager] = None,
    ):
        self.db = db or MemoryDB()
        self.ingestion_manager = ingestion_manager or IngestionManager()
        self.logger = logging.getLogger("argo_brain.tool_tracker")

    def log_tool_run(
        self,
        session_id: str,
        request: ToolRequest,
        result: ToolResult,
    ) -> None:
        """Persist tool execution to audit log with structured metrics."""
        input_payload = request.query
        output_ref = result.summary[:200] if result.summary else None

        # Database logging
        self.db.log_tool_run(
            session_id=session_id,
            tool_name=result.tool_name,
            input_payload=input_payload,
            output_ref=output_ref,
        )

        # Structured application logging
        self.logger.info(
            "Tool execution completed",
            extra={
                "tool": result.tool_name,  # Changed from tool_name to tool (matches log_setup.py formatter)
                "tool_name": result.tool_name,  # Keep both for compatibility
                "session_id": session_id,
                "input_length": len(request.query),
                "output_length": len(result.content) if result.content else 0,
                "has_snippets": bool(result.snippets),
                "snippet_count": len(result.snippets) if result.snippets else 0,
                "metadata_keys": list(result.metadata.keys()) if result.metadata else [],
            }
        )

    def process_result(
        self, session_id: str, request: ToolRequest, result: ToolResult
    ) -> None:
        """Store applicable tool outputs to knowledge base.

        Args:
            session_id: Current session ID
            request: Original tool request
            result: Tool execution result

        Side effects:
            - Logs tool run to database

        Note:
            Web fetch results are NOT cached here - WebAccessTool already
            handles ingestion directly to avoid duplicate entries in the
            vector store. See argo_brain/tools/web.py:152.
        """
        # Always log the tool run
        self.log_tool_run(session_id, request, result)

        # Note: web_access ingestion removed - handled by WebAccessTool directly
        # to prevent duplicate entries in vector store (was causing storage bloat
        # and retrieval pollution with duplicate content under different IDs).

        # Future: Cache search results, memory query results, etc.

    def recent_runs(self, session_id: str, limit: int = 10) -> List[ToolRunRecord]:
        """Retrieve recent tool executions."""
        return self.db.recent_tool_runs(session_id, limit)


__all__ = ["ToolTracker"]
