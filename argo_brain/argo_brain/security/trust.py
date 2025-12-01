"""Trust level helpers for routing and formatting context."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping

from ..config import CONFIG


class TrustLevel(str, Enum):
    """Discrete trust classifications for stored content."""

    PERSONAL_HIGH = "personal_high_trust"
    WEB_UNTRUSTED = "web_untrusted"
    TOOL_OUTPUT = "tool_output"


# Namespaces grouped by trust so policies can prioritize safer data first.
TRUSTED_NAMESPACE_MAP = {
    TrustLevel.PERSONAL_HIGH: (
        CONFIG.collections.autobiographical,
        CONFIG.collections.notes,
    ),
    TrustLevel.WEB_UNTRUSTED: (
        CONFIG.collections.web_articles,
        CONFIG.collections.web_cache,
        CONFIG.collections.youtube,
    ),
    TrustLevel.TOOL_OUTPUT: (
        CONFIG.collections.web_cache,
    ),
}


def trust_level_for_source(source_type: str | None) -> TrustLevel:
    """Return the default trust level for a given source hint."""

    if not source_type:
        return TrustLevel.WEB_UNTRUSTED
    normalized = source_type.lower()
    if normalized in {"note", "session_summary", "conversation", "profile_fact"}:
        return TrustLevel.PERSONAL_HIGH
    if normalized.startswith("youtube"):
        return TrustLevel.WEB_UNTRUSTED
    if "web" in normalized or "article" in normalized:
        return TrustLevel.WEB_UNTRUSTED
    if normalized in {"tool_output", "tool_cache"}:
        return TrustLevel.TOOL_OUTPUT
    return TrustLevel.WEB_UNTRUSTED


def ensure_trust_metadata(metadata: Mapping[str, Any], default_level: TrustLevel) -> Dict[str, Any]:
    """Return a copy of metadata that includes a trust level label."""

    trust_value = metadata.get("trust_level") if isinstance(metadata, Mapping) else None
    try:
        level = TrustLevel(trust_value) if trust_value else default_level
    except ValueError:
        level = default_level
    merged = dict(metadata)
    merged["trust_level"] = level.value
    return merged


def namespaces_for_level(level: TrustLevel) -> tuple[str, ...]:
    return TRUSTED_NAMESPACE_MAP.get(level, ())


def flatten_namespaces(levels: Iterable[TrustLevel]) -> List[str]:
    namespaces: List[str] = []
    for level in levels:
        for namespace in namespaces_for_level(level):
            if namespace not in namespaces:
                namespaces.append(namespace)
    return namespaces


__all__ = [
    "TrustLevel",
    "ensure_trust_metadata",
    "trust_level_for_source",
    "namespaces_for_level",
    "flatten_namespaces",
]
