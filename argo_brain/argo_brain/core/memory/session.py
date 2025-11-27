"""Session-level modes used to guide ingestion decisions."""

from __future__ import annotations

from enum import Enum


class SessionMode(str, Enum):
    """High-level intent for a conversation or ingestion run."""

    QUICK_LOOKUP = "quick_lookup"
    RESEARCH = "research"
    INGEST = "ingest"

    @classmethod
    def from_raw(cls, value: str | None) -> "SessionMode":
        """Convert a user-supplied string into a SessionMode."""

        if not value:
            return cls.QUICK_LOOKUP
        normalized = str(value).strip().lower()
        for mode in cls:
            if mode.value == normalized:
                return mode
        return cls.QUICK_LOOKUP
