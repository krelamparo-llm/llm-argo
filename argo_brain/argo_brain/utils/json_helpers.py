"""Utility helpers for extracting JSON objects from LLM responses."""

from __future__ import annotations

import json
from typing import Any, Optional


def extract_json_object(text: str) -> Optional[Any]:
    """Attempt to parse the first JSON object embedded in arbitrary text.

    This function extracts ONLY the first complete JSON object, not all of them.
    This ensures the model stops after generating one tool request.
    """

    stripped = (text or "").strip()
    if not stripped:
        return None

    # Remove simple ``` or ```json fences if present.
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    # Try parsing from the start if it begins with {
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            # Fall through to extract first complete object
            pass

    # Find the first complete JSON object by counting braces
    start = stripped.find("{")
    if start == -1:
        return None

    brace_count = 0
    end = start
    in_string = False
    escape_next = False

    for i in range(start, len(stripped)):
        char = stripped[i]

        # Handle string escaping
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue

        # Track if we're inside a string
        if char == '"':
            in_string = not in_string
            continue

        # Only count braces outside of strings
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    # Found the matching closing brace
                    end = i
                    break

    if brace_count == 0 and end > start:
        candidate = stripped[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    return None


__all__ = ["extract_json_object"]
