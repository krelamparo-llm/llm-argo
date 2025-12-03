"""Simple policy layer that validates LLM-proposed tool calls."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

from ..config import AppConfig, CONFIG
from ..tools.base import ToolRegistry


@dataclass
class ProposedToolCall:
    """Structured representation of a model-suggested tool call."""

    tool: str
    arguments: Dict[str, Any]


class ToolPolicy:
    """Validates tool calls before they are executed."""

    def __init__(self, config: AppConfig = CONFIG) -> None:
        self.config = config
        self.logger = logging.getLogger("argo_brain.tool_policy")

    def review(
        self,
        proposals: Iterable[ProposedToolCall],
        registry: ToolRegistry,
    ) -> Tuple[List[ProposedToolCall], List[str]]:
        """Return approved tool calls plus textual rejection reasons."""

        allowed_names = {tool.name for tool in registry.list_tools()}
        approved: List[ProposedToolCall] = []
        rejections: List[str] = []
        for proposal in proposals:
            if proposal.tool not in allowed_names:
                rejections.append(f"Tool '{proposal.tool}' is not allowed")
                continue
            validator = getattr(self, f"_validate_{proposal.tool}", None)
            arguments = dict(proposal.arguments)
            if validator:
                valid, reason, sanitized = validator(arguments)
                if not valid:
                    rejections.append(reason or f"Tool '{proposal.tool}' was rejected by policy")
                    continue
                arguments = sanitized or arguments
            proposal.arguments = arguments
            approved.append(proposal)
        if rejections:
            self.logger.warning("Tool calls rejected", extra={"reasons": rejections})
        return approved, rejections

    # --- Validators --------------------------------------------------
    def _validate_web_access(self, arguments: Dict[str, Any]) -> Tuple[bool, str | None, Dict[str, Any]]:
        url = arguments.get("url")
        if not isinstance(url, str):
            return False, "web_access requires a URL.", arguments
        parsed = urlparse(url)
        if parsed.scheme not in self.config.security.web_allowed_schemes:
            return False, f"Scheme '{parsed.scheme}' not allowed for web_access.", arguments
        if not parsed.netloc:
            return False, "URL missing network location", arguments
        allowed_hosts = self.config.security.web_allowed_hosts
        if allowed_hosts:
            hostname = parsed.hostname or ""
            if not self._host_allowed(hostname, allowed_hosts):
                return False, f"Host '{hostname}' not in allow-list", arguments
        return True, None, arguments

    def _validate_web_search(self, arguments: Dict[str, Any]) -> Tuple[bool, str | None, Dict[str, Any]]:
        """Validate web_search tool calls.

        Checks:
        - Query length within bounds (min 2, max 500 chars)
        - max_results capped at configured limit
        """
        query = arguments.get("query", "")
        if not isinstance(query, str):
            return False, "web_search query must be a string", arguments

        min_len = self.config.security.web_search_min_query_length
        max_len = self.config.security.web_search_max_query_length
        max_results_limit = self.config.security.web_search_max_results

        if len(query) < min_len:
            return False, f"Search query too short (min {min_len} chars)", arguments

        # Truncate overly long queries
        if len(query) > max_len:
            arguments["query"] = query[:max_len]
            self.logger.info(f"Truncated web_search query to {max_len} chars")

        # Cap max_results
        max_results = arguments.get("max_results")
        if max_results is not None:
            try:
                max_results_int = int(max_results)
                if max_results_int > max_results_limit:
                    arguments["max_results"] = max_results_limit
                    self.logger.info(f"Capped web_search max_results to {max_results_limit}")
            except (TypeError, ValueError):
                arguments["max_results"] = 5  # Default

        return True, None, arguments

    def _validate_memory_query(self, arguments: Dict[str, Any]) -> Tuple[bool, str | None, Dict[str, Any]]:
        top_k = arguments.get("top_k")
        try:
            top_k_int = int(top_k) if top_k is not None else 5
        except (TypeError, ValueError):
            return False, "memory_query top_k must be an integer", arguments
        max_k = max(1, self.config.security.context_max_chunks)
        if top_k_int > max_k:
            top_k_int = max_k
        arguments["top_k"] = top_k_int
        return True, None, arguments

    def _validate_memory_write(self, arguments: Dict[str, Any]) -> Tuple[bool, str | None, Dict[str, Any]]:
        """Validate memory_write tool calls.

        Checks:
        - Content size within limit (default 50KB)
        - Namespace in allow-list (if configured)
        - Metadata is a dict (if provided)
        """
        content = arguments.get("content", "")
        if not isinstance(content, str):
            return False, "memory_write content must be a string", arguments

        max_size = self.config.security.memory_write_max_content_size
        if len(content) > max_size:
            return False, f"Content exceeds max size ({max_size} chars)", arguments

        # Namespace validation
        namespace = arguments.get("namespace")
        if namespace is not None:
            allowed_namespaces = self.config.security.memory_write_allowed_namespaces
            if allowed_namespaces and namespace not in allowed_namespaces:
                return False, f"Namespace '{namespace}' not in allow-list", arguments

        # Metadata validation
        metadata = arguments.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            return False, "memory_write metadata must be a dict", arguments

        return True, None, arguments

    def _validate_retrieve_context(self, arguments: Dict[str, Any]) -> Tuple[bool, str | None, Dict[str, Any]]:
        """Validate retrieve_context tool calls.

        Checks:
        - chunk_id is present and valid format
        - chunk_id length within bounds
        """
        chunk_id = arguments.get("chunk_id")
        if not chunk_id:
            return False, "retrieve_context requires a chunk_id", arguments

        if not isinstance(chunk_id, str):
            return False, "retrieve_context chunk_id must be a string", arguments

        max_len = self.config.security.retrieve_context_max_chunk_id_length
        if len(chunk_id) > max_len:
            return False, f"chunk_id exceeds max length ({max_len} chars)", arguments

        # Basic format validation: should contain reasonable characters
        # Chunk IDs are typically like "rag:12345" or "auto:1701388800:0"
        if not chunk_id.replace(":", "").replace("-", "").replace("_", "").isalnum():
            # Allow alphanumeric, colons, hyphens, underscores
            if not re.match(r'^[\w:._-]+$', chunk_id):
                return False, "chunk_id contains invalid characters", arguments

        return True, None, arguments

    def _host_allowed(self, hostname: str, allow_list: Iterable[str]) -> bool:
        hostname = hostname.lower()
        for entry in allow_list:
            normalized = entry.lower()
            if normalized.startswith(".") and hostname.endswith(normalized):
                return True
            if hostname == normalized:
                return True
        return False


__all__ = ["ProposedToolCall", "ToolPolicy"]
