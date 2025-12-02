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
    description = """Fetch and read the full content from a specific URL.

**When to use**:
- After web_search identifies a promising source
- When you need the complete article/page content
- To verify specific claims or details from search snippets
- For deep analysis requiring full text

**Parameters**:
- url (str): Valid HTTP/HTTPS URL to fetch
  Example: "https://docs.python.org/3/library/asyncio.html"
- response_format (str, optional): "concise" or "detailed" (default: "concise")
  - "concise": Returns 200-word summary + key facts (faster, fewer tokens)
  - "detailed": Returns full article text (use for deep analysis)

**Returns**:
- Concise mode: Title, URL, summary, key facts, metadata
- Detailed mode: Full article text with metadata

**Best practices**:
- Use "concise" mode first to evaluate relevance
- Only use "detailed" mode when you need to cite specific passages
- Prefer official documentation and primary sources over secondary
- Check search snippets to confirm URL is worth fetching

**Edge cases**:
- Paywalled content may return partial text or fail
- Dynamic JavaScript sites may have limited content
- PDF links will attempt text extraction (may be slow)
- Redirects are followed automatically"""
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "HTTP(S) URL to fetch"},
            "response_format": {
                "type": "string",
                "description": "Response format: 'concise' (summary + key facts) or 'detailed' (full text)",
                "enum": ["concise", "detailed"],
                "default": "concise"
            },
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
        response_format = request.metadata.get("response_format", "concise")

        try:
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
        except requests.RequestException as exc:  # noqa: PERF203 - capturing all network errors
            error_type = type(exc).__name__
            error_message = str(exc)[:200]
            self.logger.error(
                "Web fetch failed",
                exc_info=True,
                extra={
                    "url": url,
                    "error_type": error_type,
                    "error_message": error_message,
                    "tool_name": self.name,
                },
            )
            raise ToolExecutionError(f"Failed to fetch {url}: {exc}") from exc
        final_url = self._validate_url(response.url)

        extracted = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        full_content = extracted or response.text[:4000]

        # Handle response format
        if response_format == "concise":
            content = self._generate_concise_response(full_content, final_url)
            summary = f"Retrieved concise summary from {url}"
        else:  # detailed
            content = full_content
            summary = request.metadata.get("summary") or f"Retrieved full content from {url}"

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
            "response_format": response_format,
            "full_length": len(full_content),
            "word_count": len(full_content.split()),
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

    def _generate_concise_response(self, content: str, url: str) -> str:
        """Generate a concise summary of the content with key facts.

        Returns a structured response with:
        - Summary (first few paragraphs or ~200 words)
        - Key Facts (bullet points from content)
        """
        if not content or len(content) < 100:
            return content

        # Extract first few paragraphs for summary
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

        # Summary: First 3 paragraphs or ~200 words, whichever is shorter
        summary_paras = []
        word_count = 0
        for para in paragraphs[:5]:
            words_in_para = len(para.split())
            if word_count + words_in_para > 250:
                # Truncate this paragraph to hit ~200 words
                remaining_words = 250 - word_count
                truncated = ' '.join(para.split()[:remaining_words]) + "..."
                summary_paras.append(truncated)
                break
            summary_paras.append(para)
            word_count += words_in_para
            if word_count >= 200:
                break

        summary = '\n\n'.join(summary_paras)

        # Extract key facts: look for lists, numbered items, or sentences with numbers/dates
        key_facts = []
        for para in paragraphs:
            # Detect bullet points or numbered lists
            if any(para.strip().startswith(marker) for marker in ['•', '-', '*', '1.', '2.', '3.']):
                items = [line.strip() for line in para.split('\n') if line.strip()]
                key_facts.extend(items[:3])  # Take first 3 items
                if len(key_facts) >= 5:
                    break
            # Detect sentences with numbers, dates, or percentages
            elif any(indicator in para for indicator in ['%', '20', '$', 'million', 'billion']):
                sentences = para.split('. ')
                for sent in sentences[:2]:
                    if any(char.isdigit() for char in sent):
                        key_facts.append(sent.strip())
                        if len(key_facts) >= 5:
                            break

        # Format the response
        result = f"**Summary**:\n{summary}\n\n"

        if key_facts:
            result += "**Key Facts**:\n"
            for fact in key_facts[:5]:  # Limit to 5 key facts
                # Clean up fact formatting
                clean_fact = fact.lstrip('•-*123456789. ').strip()
                if clean_fact:
                    result += f"• {clean_fact}\n"

        result += f"\n**Full article available at**: {url}\n"
        result += f"**Note**: Use response_format='detailed' to get full text for deep analysis.\n"

        return result

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
