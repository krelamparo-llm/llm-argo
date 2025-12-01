"""Ingestion pipeline coordinating embeddings, vector storage, and policies."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence
from uuid import uuid4

import numpy as np

from ...config import CONFIG
from ...embeddings import embed_texts
from ..vector_store.factory import create_vector_store
from .document import SourceDocument
from ...security import TrustLevel, ensure_trust_metadata, trust_level_for_source

Metadata = Dict[str, Any]


def _default_embedder(texts: Sequence[str]) -> List[List[float]]:
    return embed_texts(texts)


@dataclass
class IngestionManager:
    """Coordinates chunking and vector store writes for document ingestion."""

    vector_store: Optional[Any] = None
    embedder: Optional[Callable[[Sequence[str]], List[List[float]]]] = None
    chunk_size: int = 800
    chunk_overlap: int = 200

    def __post_init__(self) -> None:
        self.config = CONFIG
        self.vector_store = self.vector_store or create_vector_store()
        self.embedder = self.embedder or _default_embedder

    # Public API ---------------------------------------------------------
    def ingest_document(
        self,
        doc: SourceDocument,
        *,
        ephemeral: bool = False,
    ) -> None:
        """Store document chunks in appropriate namespace.

        Args:
            doc: The document to ingest
            ephemeral: If True, store in web_cache with TTL metadata
        """
        self._trust_level_for_doc(doc)
        body = doc.content()
        if not body:
            return

        # Determine namespace from source type
        namespace = self._namespace_for_source_type(doc.source_type)

        # Chunk the text
        chunks = self._chunk_text(body)

        # Add TTL metadata if ephemeral
        metadata_overrides = {}
        if ephemeral:
            namespace = self.config.collections.web_cache
            metadata_overrides["fetched_at"] = int(time.time())

        # Store chunks
        self._upsert_chunks(
            namespace=namespace,
            doc=doc,
            chunks=chunks,
            metadata_overrides=metadata_overrides,
        )

    def _upsert_chunks(
        self,
        *,
        namespace: str,
        doc: SourceDocument,
        chunks: List[str],
        metadata_overrides: Optional[Metadata] = None,
    ) -> None:
        if not chunks:
            return
        embeddings = self.embedder(chunks)
        if not embeddings:
            return
        vectors = np.array(embeddings, dtype=float)
        metadatas: List[Metadata] = []
        ids: List[str] = []
        timestamp = int(time.time())
        for idx, chunk in enumerate(chunks):
            meta = self._base_metadata(doc)
            meta.update(
                {
                    "chunk_index": idx,
                    "ingested_ts": timestamp,
                }
            )
            if metadata_overrides:
                meta.update(metadata_overrides)
            metadatas.append(meta)
            ids.append(self._chunk_id(doc, idx))
        self.vector_store.add(
            namespace=namespace,
            texts=chunks,
            embeddings=vectors,
            metadatas=metadatas,
            ids=ids,
        )

    # Utility helpers ----------------------------------------------------
    def _chunk_text(self, text: str) -> List[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        chunks: List[str] = []
        start = 0
        length = len(cleaned)
        while start < length:
            end = min(start + self.chunk_size, length)
            chunks.append(cleaned[start:end])
            if end >= length:
                break
            start = max(0, end - self.chunk_overlap)
        return chunks

    def _base_metadata(self, doc: SourceDocument) -> Metadata:
        metadata = dict(doc.metadata)
        metadata.setdefault("source_id", doc.id)
        metadata.setdefault("source_type", doc.source_type)
        if doc.url:
            metadata.setdefault("url", doc.url)
        if doc.title:
            metadata.setdefault("title", doc.title)
        trust_value = metadata.get("trust_level")
        try:
            TrustLevel(trust_value)
        except (ValueError, TypeError):
            metadata["trust_level"] = trust_level_for_source(metadata.get("source_type")).value
        return metadata

    def _trust_level_for_doc(self, doc: SourceDocument) -> TrustLevel:
        metadata = doc.metadata or {}
        trust_value = metadata.get("trust_level")
        try:
            level = TrustLevel(trust_value)
        except (ValueError, TypeError):
            level = trust_level_for_source(doc.source_type)
        doc.metadata = ensure_trust_metadata(metadata, level)
        return level

    def _chunk_id(self, doc: SourceDocument, suffix: Any) -> str:
        return f"{doc.id}:{suffix}:{uuid4().hex[:8]}"

    def _namespace_for_source_type(self, source_type: str) -> str:
        """Map source type directly to namespace (content-type based).

        This implements the observation-first model: content goes to the
        namespace matching where it came from, not based on trust level.
        """
        source_type = (source_type or "").lower()

        # YouTube content → youtube_history
        if source_type.startswith("youtube"):
            return self.config.collections.youtube

        # High-trust personal content → notes_journal
        if source_type in ("note", "journal", "explicit_save", "research_memo"):
            return self.config.collections.notes

        # Browser history, web pages, articles → reading_history
        if source_type in ("browser_history", "web_page", "article", "web_article"):
            return self.config.collections.web_articles

        # Tool outputs during research → web_cache (though ephemeral flag usually handles this)
        if source_type in ("tool_output", "tool_cache"):
            return self.config.collections.web_cache

        # Default: reading history (for observation-first model)
        return self.config.collections.web_articles


_DEFAULT_MANAGER: Optional[IngestionManager] = None


def get_default_ingestion_manager() -> IngestionManager:
    """Return a cached ingestion manager shared across tools."""

    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = IngestionManager()
    return _DEFAULT_MANAGER


__all__ = ["IngestionManager", "get_default_ingestion_manager"]
