"""Utility helpers for extracting JSON objects from LLM responses."""

from __future__ import annotations

import json
from typing import Any, Optional


def extract_json_object(text: str) -> Optional[Any]:
    """Attempt to parse the first JSON object embedded in arbitrary text."""

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

    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = stripped[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    return None


__all__ = ["extract_json_object"]
