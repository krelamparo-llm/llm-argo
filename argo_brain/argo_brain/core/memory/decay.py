"""Time-based decay scoring and TTL filtering for memory retrieval."""

from __future__ import annotations

import math
import time
from typing import Any, List, Optional

from ...config import CONFIG


def apply_decay_scoring(
    chunks: List[Any],  # List of Document or RetrievedChunk with .score and .metadata
    namespace: str,
    current_time: Optional[int] = None,
) -> List[Any]:
    """Apply time-based decay to chunk scores.

    Decay formula: score *= 0.5^(age / half_life)

    Args:
        chunks: List of chunks with .score and .metadata attributes
        namespace: Namespace to get retention policy for
        current_time: Unix timestamp (default: now)

    Returns:
        Chunks with decayed scores, re-sorted by new scores
    """
    policy = CONFIG.collections.get_policy(namespace)
    if not policy.enable_decay:
        return chunks  # No decay for this namespace

    current_time = current_time or int(time.time())
    half_life_seconds = policy.decay_half_life_days * 86400

    decayed_chunks = []
    for chunk in chunks:
        # Get timestamp from metadata
        metadata = getattr(chunk, "metadata", {}) or {}
        ingested_ts = metadata.get("ingested_ts", current_time)

        # Calculate age
        age_seconds = current_time - ingested_ts
        if age_seconds < 0:
            age_seconds = 0  # Future timestamps → no decay

        # Calculate decay factor: 0.5^(age / half_life)
        decay_factor = math.pow(0.5, age_seconds / half_life_seconds)

        # Apply decay to score
        if hasattr(chunk, "score") and chunk.score is not None:
            original_score = chunk.score
            chunk.score = original_score * decay_factor

        decayed_chunks.append(chunk)

    # Re-sort by decayed score (descending)
    decayed_chunks.sort(key=lambda c: getattr(c, "score", 0) or 0, reverse=True)

    return decayed_chunks


def filter_expired(
    chunks: List[Any],
    namespace: str,
    current_time: Optional[int] = None,
) -> List[Any]:
    """Remove chunks older than TTL.

    Args:
        chunks: List of chunks with .metadata attribute
        namespace: Namespace to get retention policy for
        current_time: Unix timestamp (default: now)

    Returns:
        Filtered list of non-expired chunks
    """
    policy = CONFIG.collections.get_policy(namespace)
    if policy.ttl_days is None:
        return chunks  # No expiration

    current_time = current_time or int(time.time())
    max_age_seconds = policy.ttl_days * 86400

    filtered = []
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {}) or {}
        ingested_ts = metadata.get("ingested_ts") or metadata.get("fetched_at")

        if ingested_ts is None:
            # No timestamp → assume current (don't filter)
            filtered.append(chunk)
            continue

        age_seconds = current_time - ingested_ts

        if age_seconds <= max_age_seconds:
            filtered.append(chunk)

    return filtered


__all__ = ["apply_decay_scoring", "filter_expired"]
