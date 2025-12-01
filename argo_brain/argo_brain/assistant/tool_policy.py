"""Simple policy layer that validates LLM-proposed tool calls."""

from __future__ import annotations

import logging
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
