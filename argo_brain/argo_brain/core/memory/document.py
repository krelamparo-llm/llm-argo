"""Shared document abstraction for ingestion and tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SourceDocument:
    """Represents a fetched resource prior to ingestion."""

    id: str
    source_type: str
    raw_text: str
    cleaned_text: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def content(self) -> str:
        """Return the preferred text body for chunking/embedding."""

        return (self.cleaned_text or self.raw_text or "").strip()
