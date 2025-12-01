"""Web search tool implementation using DuckDuckGo."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..config import CONFIG
from .base import Tool, ToolExecutionError, ToolRequest, ToolResult


class WebSearchTool:
    """Performs web searches and returns URLs + snippets."""

    name = "web_search"
    description = (
        "Search the web for information. Returns URLs and text snippets. "
        "Use this when you need to find information not in memory. "
        "Example: web_search('RAG retention policies best practices')"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (2-100 chars)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 5, max 10)",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "snippet": {"type": "string"},
                    },
                },
            },
            "metadata": {"type": "object"},
        },
    }
    side_effects = "external_network"

    def __init__(
        self,
        *,
        backend: str = "duckduckgo",
        searxng_url: Optional[str] = None,
        max_results_limit: int = 10,
    ):
        """Initialize web search tool.

        Args:
            backend: Search backend ('duckduckgo' or 'searxng')
            searxng_url: URL for SearXNG instance (if using that backend)
            max_results_limit: Hard cap on results (default 10)
        """
        self.backend = backend
        self.searxng_url = searxng_url
        self.max_results_limit = max_results_limit
        self.security = CONFIG.security
        self.logger = logging.getLogger("argo_brain.tools.search")

    def run(self, request: ToolRequest) -> ToolResult:
        """Execute web search."""
        query = request.query
        if not query or len(query) < 2:
            raise ToolExecutionError("Query too short (minimum 2 characters)")
        if len(query) > 100:
            raise ToolExecutionError("Query too long (maximum 100 characters)")

        max_results = request.metadata.get("max_results", 5)
        if isinstance(max_results, int):
            max_results = min(max_results, self.max_results_limit)
        else:
            max_results = 5

        # Choose backend
        if self.backend == "searxng" and self.searxng_url:
            results = self._search_searxng(query, max_results)
        else:
            results = self._search_duckduckgo(query, max_results)

        summary = f"Found {len(results)} search results for: {query}"
        snippets = [f"{r['title']}: {r['snippet'][:200]}" for r in results[:3]]

        self.logger.info(
            "Web search completed",
            extra={
                "session_id": request.session_id,
                "query": query,
                "result_count": len(results),
                "backend": self.backend,
            },
        )

        return ToolResult(
            tool_name=self.name,
            summary=summary,
            content=self._format_results(results),
            metadata={
                "query": query,
                "result_count": len(results),
                "backend": self.backend,
            },
            snippets=snippets,
        )

    def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Use DuckDuckGo HTML scraping (no API key needed)."""
        try:
            from ddgs import DDGS
        except ImportError:
            # Fallback to old package name for backward compatibility
            try:
                from duckduckgo_search import DDGS
            except ImportError as e:
                raise ToolExecutionError(
                    "ddgs not installed. Run: pip install ddgs"
                ) from e

        try:
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            results = []
            for r in raw_results[:max_results]:
                results.append(
                    {
                        "title": r.get("title", "No title"),
                        "url": r.get("href", r.get("link", "")),
                        "snippet": r.get("body", r.get("snippet", "")),
                    }
                )
            return results
        except Exception as e:
            self.logger.error(
                "DuckDuckGo search failed",
                exc_info=True,
                extra={"query": query, "error": str(e)},
            )
            raise ToolExecutionError(f"DuckDuckGo search failed: {e}") from e

    def _search_searxng(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Use local SearXNG instance (privacy-focused metasearch)."""
        if not self.searxng_url:
            raise ToolExecutionError("SearXNG URL not configured")

        import requests

        params = {
            "q": query,
            "format": "json",
            "categories": "general",
        }

        try:
            response = requests.get(
                f"{self.searxng_url}/search",
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for r in data.get("results", [])[:max_results]:
                results.append(
                    {
                        "title": r.get("title", "No title"),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                    }
                )
            return results
        except Exception as e:
            self.logger.error(
                "SearXNG search failed",
                exc_info=True,
                extra={"query": query, "error": str(e)},
            )
            raise ToolExecutionError(f"SearXNG search failed: {e}") from e

    def _format_results(self, results: List[Dict[str, str]]) -> str:
        """Format results as readable text."""
        if not results:
            return "No results found."

        lines = []
        for idx, r in enumerate(results, 1):
            lines.append(f"{idx}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            snippet = r['snippet'][:300]
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")

        return "\n".join(lines)


__all__ = ["WebSearchTool"]
