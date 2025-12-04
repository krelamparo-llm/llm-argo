"""JSON-based tool call parser for models that wrap JSON in <tool_call> tags.

Expected common formats:
- Single call: <tool_call>{"name": "web_search", "arguments": {"query": "example"}}</tool_call>
- Multiple calls: <tool_call>[{...}, {...}]</tool_call>
- Concatenated calls or bare JSON without tags.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional


class JSONToolParser:
    """Parse JSON-formatted tool calls wrapped in <tool_call> tags."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("argo_brain.json_parser")
        # Match contents between <tool_call>...</tool_call>, case-insensitive, tolerant of whitespace/newlines
        self.tool_call_regex = re.compile(r"<tool_call>(.*?)</tool_call>", re.IGNORECASE | re.DOTALL)
        # Fallback: find balanced JSON objects/arrays in text
        self.brace_pattern = re.compile(r"[\\{\\}\\[\\]]")

    def extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract tool calls from model output."""
        if not text:
            return []

        calls: List[Dict[str, Any]] = []

        blocks = self._get_tool_blocks(text)
        for block in blocks:
            # First, try to parse the whole block (object or array)
            parsed = self._parse_json_block(block)
            if parsed:
                calls.extend(parsed)
                continue

            # Otherwise, scan for embedded JSON candidates and parse them
            for candidate in self._json_candidates(block):
                parsed_candidate = self._parse_json_block(candidate)
                if parsed_candidate:
                    calls.extend(parsed_candidate)
                else:
                    self.logger.debug("Skipping unparsable candidate: %s", candidate[:200])

        return calls

    def _get_tool_blocks(self, text: str) -> List[str]:
        """Split text into potential tool_call payloads."""
        matches = [m.strip() for m in self.tool_call_regex.findall(text)]
        if matches:
            return matches

        # No tags found; treat full text as one block
        stripped = text.strip()
        return [stripped] if stripped else []

    def _parse_json_block(self, block: str) -> List[Dict[str, Any]]:
        """Parse a block that should contain one or more JSON tool calls."""
        block = block.strip()
        if not block:
            return []

        # Try direct JSON load
        obj = self._safe_json_load(block)
        if obj is None:
            return []

        return self._normalize_obj(obj)

    def _safe_json_load(self, candidate: str) -> Optional[Any]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    def _normalize_obj(self, obj: Any) -> List[Dict[str, Any]]:
        """Normalize parsed JSON into our call shape."""
        calls: List[Dict[str, Any]] = []

        # OpenAI-style tool_calls array wrapper
        if isinstance(obj, dict) and "tool_calls" in obj and isinstance(obj["tool_calls"], list):
            for item in obj["tool_calls"]:
                normalized = self._normalize_single(item)
                if normalized:
                    calls.append(normalized)
            return calls

        # Single object
        if isinstance(obj, dict):
            normalized = self._normalize_single(obj)
            if normalized:
                calls.append(normalized)
            return calls

        # Array of objects
        if isinstance(obj, list):
            for item in obj:
                normalized = self._normalize_single(item)
                if normalized:
                    calls.append(normalized)
            return calls

        return []

    def _normalize_single(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Normalize one tool call object."""
        if not isinstance(obj, dict):
            return None

        name = obj.get("name") or obj.get("tool") or obj.get("function") or obj.get("id")
        if not name:
            return None

        args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
        if isinstance(args, str):
            loaded = self._safe_json_load(args)
            if loaded is not None:
                args = loaded

        # If args isn't a dict after parsing, wrap it
        if not isinstance(args, dict):
            args = {"value": args}

        return {"tool": str(name), "arguments": args}

    def _json_candidates(self, text: str) -> List[str]:
        """Find balanced JSON-looking segments inside text."""
        candidates: List[str] = []
        stack = []
        start_idx: Optional[int] = None
        for idx, char in enumerate(text):
            if char in "{[":
                if not stack:
                    start_idx = idx
                stack.append(char)
            elif char in "]}":
                if stack:
                    stack.pop()
                    if not stack and start_idx is not None:
                        candidates.append(text[start_idx : idx + 1].strip())
                        start_idx = None
        return candidates
