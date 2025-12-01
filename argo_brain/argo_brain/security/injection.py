"""Prompt-injection heuristics used to filter retrieved context."""

from __future__ import annotations

from typing import Iterable, Sequence


def is_suspicious_text(text: str, phrases: Sequence[str]) -> bool:
    """Return True if any suspicious phrase is present in the text."""

    lowered = text.lower()
    return any(phrase.lower() in lowered for phrase in phrases)


def filter_suspicious_chunks(
    chunks: Iterable[tuple[str, dict]],
    phrases: Sequence[str],
) -> list[tuple[str, dict]]:
    """Drop chunks containing obvious prompt-injection attempts."""

    filtered: list[tuple[str, dict]] = []
    for text, metadata in chunks:
        if not text:
            continue
        if is_suspicious_text(text, phrases):
            continue
        filtered.append((text, metadata))
    return filtered


__all__ = ["is_suspicious_text", "filter_suspicious_chunks"]
