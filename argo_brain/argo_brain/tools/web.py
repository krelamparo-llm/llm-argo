"""Web access tool implementation."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse
import logging

import requests
import trafilatura

from ..core.memory.document import SourceDocument
from ..core.memory.ingestion import IngestionManager, get_default_ingestion_manager
from ..config import CONFIG
from ..security import TrustLevel
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
        self.security = CONFIG.security
        self.logger = logging.getLogger("argo_brain.tools.web")

    def run(self, request: ToolRequest) -> ToolResult:
        url = request.metadata.get("url") or request.query
        url = self._validate_url(url)

        try:
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
        except requests.RequestException as exc:  # noqa: PERF203 - capturing all network errors
            raise ToolExecutionError(f"Failed to fetch {url}: {exc}") from exc
        final_url = self._validate_url(response.url)

        extracted = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        content = extracted or response.text[:4000]
        summary = request.metadata.get("summary") or f"Retrieved {url}"

        # Determine if this is ephemeral (deep research) or archival
        # For now, treat as ephemeral - future browser history daemon will use archival
        ephemeral = True
        src_type = "live_web"

        metadata: Dict[str, Any] = {
            "url": final_url,
            "fetched_at": int(time.time()),
            "session_id": request.session_id,
            "source_id": request.metadata.get("source_id", url),
            "trust_level": TrustLevel.WEB_UNTRUSTED.value,
            "http_status": response.status_code,
            "source_type": src_type,
        }
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
        self.ingestion_manager.ingest_document(doc, ephemeral=ephemeral)
        metadata["source_type"] = doc.source_type
        metadata["ingested"] = True
        self.logger.info(
            "WebAccessTool fetched",
            extra={
                "session_id": request.session_id,
                "url": final_url,
                "status": response.status_code,
            },
        )
        return ToolResult(
            tool_name=self.name,
            summary=summary,
            content=content,
            metadata=metadata,
            snippets=snippets,
        )

    def _validate_url(self, url: Optional[str]) -> str:
        if not url:
            raise ToolExecutionError("WebAccessTool requires a URL")
        parsed = urlparse(url)
        if parsed.scheme not in self.security.web_allowed_schemes:
            raise ToolExecutionError(f"URL scheme '{parsed.scheme}' is not allowed")
        if not parsed.netloc:
            raise ToolExecutionError("URL must include a host")
        allowed_hosts = self.security.web_allowed_hosts
        if allowed_hosts:
            hostname = parsed.hostname or ""
            normalized = hostname.lower()
            allowed = False
            for entry in allowed_hosts:
                entry_norm = entry.lower()
                if entry_norm.startswith(".") and normalized.endswith(entry_norm):
                    allowed = True
                    break
                if normalized == entry_norm:
                    allowed = True
                    break
            if not allowed:
                raise ToolExecutionError(f"Host '{hostname}' is not allow-listed")
        return parsed.geturl()
