"""Web access tool implementation."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests
import trafilatura

from ..core.memory.document import SourceDocument
from ..core.memory.ingestion import IngestionManager, get_default_ingestion_manager
from ..core.memory.session import SessionMode
from .base import Tool, ToolExecutionError, ToolRequest, ToolResult


class WebAccessTool:
    """Fetches a web page and returns extracted text for downstream use."""

    name = "web_access"
    description = "Fetch a URL via HTTP(S) and extract readable text."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "HTTP(S) URL to fetch"},
            "summary": {"type": "string", "description": "Optional summary to log with the result"},
        },
        "required": ["url"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Extracted plain text"},
            "metadata": {"type": "object", "description": "Details such as URL and timestamp"},
        },
    }
    side_effects = "external_network"

    def __init__(
        self,
        *,
        timeout: int = 20,
        user_agent: Optional[str] = None,
        ingestion_manager: Optional[IngestionManager] = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or "ArgoWebTool/1.0 (+https://argo.local)"
        self.ingestion_manager = ingestion_manager or get_default_ingestion_manager()

    def run(self, request: ToolRequest) -> ToolResult:
        url = request.metadata.get("url") or request.query
        if not url or not url.startswith(("http://", "https://")):
            raise ToolExecutionError("WebAccessTool requires an http(s) URL in the query or metadata['url']")

        try:
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
        except requests.RequestException as exc:  # noqa: PERF203 - capturing all network errors
            raise ToolExecutionError(f"Failed to fetch {url}: {exc}") from exc

        extracted = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        content = extracted or response.text[:4000]
        summary = request.metadata.get("summary") or f"Retrieved {url}"
        metadata: Dict[str, Any] = {
            "url": url,
            "fetched_at": int(time.time()),
            "session_id": request.session_id,
            "source_id": request.metadata.get("source_id", url),
        }
        session_mode = request.session_mode
        src_type = "live_web" if session_mode == SessionMode.QUICK_LOOKUP else "web_article"
        metadata["source_type"] = src_type
        snippets = [content[:500]] if content else []
        doc = SourceDocument(
            id=str(metadata["source_id"]),
            source_type=src_type,
            raw_text=response.text,
            cleaned_text=content,
            url=url,
            title=request.metadata.get("title"),
            metadata=metadata,
        )
        self.ingestion_manager.ingest_document(doc, session_mode=session_mode)
        metadata["source_type"] = doc.source_type
        metadata["ingested"] = True
        return ToolResult(
            tool_name=self.name,
            summary=summary,
            content=content,
            metadata=metadata,
            snippets=snippets,
        )
