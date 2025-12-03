"""Prompt sanitization utilities for safe context/tool result injection.

This module provides sanitization functions to prevent prompt injection attacks
and ensure clean integration of untrusted content into prompts.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("argo_brain.prompt_sanitizer")


@dataclass
class SanitizationResult:
    """Result of sanitization operation."""

    content: str
    original_length: int
    sanitized_length: int
    was_truncated: bool
    was_modified: bool
    modifications: list[str]


class PromptSanitizer:
    """Sanitizes untrusted content before injection into prompts.

    Handles:
    - XML tag escaping to prevent prompt structure breaking
    - System message marker neutralization
    - Truncation with clear indicators
    - Audit logging of modifications
    """

    # Patterns that could break prompt structure or confuse the model
    DANGEROUS_PATTERNS = [
        (r"<\|im_start\|>", "[IM_START]"),  # Chat template markers
        (r"<\|im_end\|>", "[IM_END]"),
        (r"\[SYSTEM\]", "[CONTEXT-SYSTEM]"),  # System message markers
        (r"\[INST\]", "[CONTEXT-INST]"),
        (r"\[/INST\]", "[CONTEXT-/INST]"),
        (r"<<SYS>>", "[[SYS]]"),
        (r"<</SYS>>", "[[/SYS]]"),
    ]

    # XML-like tags that should be escaped in user content
    XML_ESCAPE_MAP = {
        "<tool_call>": "&lt;tool_call&gt;",
        "</tool_call>": "&lt;/tool_call&gt;",
        "<function": "&lt;function",
        "</function>": "&lt;/function&gt;",
        "<parameter": "&lt;parameter",
        "</parameter>": "&lt;/parameter&gt;",
        "<think>": "&lt;think&gt;",
        "</think>": "&lt;/think&gt;",
        "<research_plan>": "&lt;research_plan&gt;",
        "</research_plan>": "&lt;/research_plan&gt;",
        "<synthesis>": "&lt;synthesis&gt;",
        "</synthesis>": "&lt;/synthesis&gt;",
    }

    def __init__(
        self,
        max_length: int = 10000,
        escape_xml: bool = True,
        neutralize_markers: bool = True,
    ):
        """Initialize sanitizer with configuration.

        Args:
            max_length: Maximum allowed content length (0 = no limit)
            escape_xml: Whether to escape XML-like tags
            neutralize_markers: Whether to neutralize system message markers
        """
        self.max_length = max_length
        self.escape_xml = escape_xml
        self.neutralize_markers = neutralize_markers

    def sanitize(self, content: str, source: str = "unknown") -> SanitizationResult:
        """Sanitize untrusted content for safe prompt injection.

        Args:
            content: The untrusted content to sanitize
            source: Identifier for logging (e.g., "tool_result", "rag_context")

        Returns:
            SanitizationResult with sanitized content and metadata
        """
        if not content:
            return SanitizationResult(
                content="",
                original_length=0,
                sanitized_length=0,
                was_truncated=False,
                was_modified=False,
                modifications=[],
            )

        original_length = len(content)
        modifications = []
        sanitized = content

        # Step 1: Neutralize dangerous markers
        if self.neutralize_markers:
            for pattern, replacement in self.DANGEROUS_PATTERNS:
                if re.search(pattern, sanitized, re.IGNORECASE):
                    sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
                    modifications.append(f"neutralized: {pattern}")

        # Step 2: Escape XML-like tags that could confuse tool parsing
        if self.escape_xml:
            for tag, escaped in self.XML_ESCAPE_MAP.items():
                if tag in sanitized:
                    sanitized = sanitized.replace(tag, escaped)
                    modifications.append(f"escaped: {tag}")

        # Step 3: Truncate if too long
        was_truncated = False
        if self.max_length > 0 and len(sanitized) > self.max_length:
            sanitized = sanitized[: self.max_length]
            sanitized += f"\n\n[TRUNCATED - original: {original_length} chars, showing first {self.max_length}]"
            was_truncated = True
            modifications.append(f"truncated: {original_length} → {self.max_length}")

        was_modified = len(modifications) > 0

        if was_modified:
            logger.debug(
                f"Sanitized content from {source}",
                extra={
                    "source": source,
                    "original_length": original_length,
                    "sanitized_length": len(sanitized),
                    "modifications": modifications,
                },
            )

        return SanitizationResult(
            content=sanitized,
            original_length=original_length,
            sanitized_length=len(sanitized),
            was_truncated=was_truncated,
            was_modified=was_modified,
            modifications=modifications,
        )

    def sanitize_tool_result(self, content: str, tool_name: str) -> str:
        """Convenience method for sanitizing tool results.

        Args:
            content: Tool result content
            tool_name: Name of the tool for logging

        Returns:
            Sanitized content string
        """
        result = self.sanitize(content, source=f"tool:{tool_name}")
        return result.content

    def sanitize_context(self, content: str, context_type: str = "rag") -> str:
        """Convenience method for sanitizing RAG context.

        Args:
            content: Context content
            context_type: Type of context for logging

        Returns:
            Sanitized content string
        """
        result = self.sanitize(content, source=f"context:{context_type}")
        return result.content


def compute_prompt_hash(messages: list) -> str:
    """Compute a hash of the prompt for traceability.

    Args:
        messages: List of chat messages

    Returns:
        12-character hash string
    """
    content = "\n---\n".join(
        f"{getattr(m, 'role', 'unknown')}: {getattr(m, 'content', str(m))}"
        for m in messages
    )
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def compute_prompt_stats(messages: list) -> dict:
    """Compute statistics about a prompt for logging.

    Args:
        messages: List of chat messages

    Returns:
        Dictionary with prompt statistics
    """
    total_chars = sum(len(getattr(m, "content", "")) for m in messages)
    system_count = sum(1 for m in messages if getattr(m, "role", "") == "system")
    user_count = sum(1 for m in messages if getattr(m, "role", "") == "user")
    assistant_count = sum(1 for m in messages if getattr(m, "role", "") == "assistant")

    return {
        "message_count": len(messages),
        "total_chars": total_chars,
        "system_messages": system_count,
        "user_messages": user_count,
        "assistant_messages": assistant_count,
        "prompt_hash": compute_prompt_hash(messages),
    }


# Default sanitizer instance
DEFAULT_SANITIZER = PromptSanitizer()


__all__ = [
    "PromptSanitizer",
    "SanitizationResult",
    "compute_prompt_hash",
    "compute_prompt_stats",
    "DEFAULT_SANITIZER",
]
