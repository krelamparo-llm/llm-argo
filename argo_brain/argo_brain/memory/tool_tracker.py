"""Tool execution tracking and web result caching."""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import uuid4

from ..core.memory.document import SourceDocument
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
                "tool_name": result.tool_name,
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
            - Caches web fetch results in ephemeral web_cache
        """
        # Always log the tool run
        self.log_tool_run(session_id, request, result)

        # Cache web results if applicable
        if result.tool_name == "web_access" and result.content:
            self._cache_web_content(result)

        # Future: Cache search results, memory query results, etc.

    def recent_runs(self, session_id: str, limit: int = 10) -> List[ToolRunRecord]:
        """Retrieve recent tool executions."""
        return self.db.recent_tool_runs(session_id, limit)

    def _cache_web_content(self, result: ToolResult) -> None:
        """Store web fetch result in ephemeral cache."""
        metadata = result.metadata or {}
        url = metadata.get("url", "unknown")

        doc = SourceDocument(
            id=f"tool-{uuid4().hex}",
            source_type="tool_output",
            raw_text=result.content,
            cleaned_text=result.content,
            url=url,
            title=metadata.get("title"),
            metadata=metadata,
        )

        self.ingestion_manager.ingest_document(doc, ephemeral=True)

        self.logger.info(
            "Cached web tool result",
            extra={"url": url, "content_length": len(result.content)},
        )


__all__ = ["ToolTracker"]
