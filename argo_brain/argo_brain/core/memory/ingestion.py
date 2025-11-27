"""Ingestion pipeline coordinating embeddings, vector storage, and policies."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence
from uuid import uuid4

import numpy as np

from ...config import CONFIG
from ...embeddings import embed_texts
from ...llm_client import ChatMessage, LLMClient
from ..vector_store.factory import create_vector_store
from .document import SourceDocument
from .session import SessionMode

Metadata = Dict[str, Any]


class IngestionPolicy(str, Enum):
    """Controls how aggressively a document is persisted."""

    EPHEMERAL = "ephemeral"
    SUMMARY_ONLY = "summary_only"
    FULL = "full"


def _default_embedder(texts: Sequence[str]) -> List[List[float]]:
    return embed_texts(texts)


@dataclass
class IngestionManager:
    """Coordinates chunking, summarization, and vector store writes."""

    vector_store: Optional[Any] = None
    llm_client: Optional[LLMClient] = None
    embedder: Optional[Callable[[Sequence[str]], List[List[float]]]] = None
    chunk_size: int = 800
    chunk_overlap: int = 200

    def __post_init__(self) -> None:
        self.config = CONFIG
        self.vector_store = self.vector_store or create_vector_store()
        self.llm_client = self.llm_client or LLMClient()
        self.embedder = self.embedder or _default_embedder

    # Public API ---------------------------------------------------------
    def ingest_document(
        self,
        doc: SourceDocument,
        *,
        session_mode: SessionMode = SessionMode.QUICK_LOOKUP,
        user_intent: Optional[str] = None,
        policy_override: Optional[IngestionPolicy] = None,
    ) -> None:
        """Decide a policy and persist the document accordingly."""

        body = doc.content()
        if not body:
            return
        policy = policy_override or self._decide_policy(doc, session_mode, user_intent)
        if policy == IngestionPolicy.EPHEMERAL:
            self._store_ephemeral(doc, body)
            return
        if policy == IngestionPolicy.SUMMARY_ONLY:
            summary = self._summarize(body, doc)
            if summary:
                self._store_summary(doc, summary)
            return
        if policy == IngestionPolicy.FULL:
            self._store_full(doc, body)
            return
        raise ValueError(f"Unsupported ingestion policy: {policy}")

    # Policy helpers -----------------------------------------------------
    def _decide_policy(
        self,
        doc: SourceDocument,
        session_mode: SessionMode,
        user_intent: Optional[str],
    ) -> IngestionPolicy:
        override = doc.metadata.get("ingestion_policy")
        if isinstance(override, str):
            try:
                return IngestionPolicy(override)
            except ValueError:
                pass
        if user_intent == "explicit_save":
            return IngestionPolicy.FULL
        if session_mode == SessionMode.INGEST:
            return IngestionPolicy.FULL
        if session_mode == SessionMode.RESEARCH:
            return IngestionPolicy.FULL if len(doc.content()) > 1200 else IngestionPolicy.SUMMARY_ONLY
        if doc.source_type == "live_web":
            return IngestionPolicy.EPHEMERAL
        if len(doc.content()) < 600:
            return IngestionPolicy.FULL
        return IngestionPolicy.SUMMARY_ONLY

    # Storage helpers ----------------------------------------------------
    def _store_ephemeral(self, doc: SourceDocument, text: str) -> None:
        chunks = self._chunk_text(text)
        self._upsert_chunks(
            namespace=self.config.collections.web_cache,
            doc=doc,
            chunks=chunks,
            metadata_overrides={"fetched_at": int(time.time())},
        )

    def _store_full(self, doc: SourceDocument, text: str) -> None:
        namespace = self._namespace_for(doc)
        chunks = self._chunk_text(text)
        self._upsert_chunks(namespace=namespace, doc=doc, chunks=chunks)
        summary = self._summarize(text, doc)
        if summary:
            self._store_summary(doc, summary)

    def _store_summary(self, doc: SourceDocument, summary: str) -> None:
        namespace = self.config.collections.notes
        embeddings = self._embedder([summary])
        if not embeddings:
            return
        vectors = np.array(embeddings, dtype=float)
        metadata = self._base_metadata(doc)
        metadata.update({"kind": "summary"})
        self.vector_store.add(
            namespace=namespace,
            texts=[summary],
            embeddings=vectors,
            metadatas=[metadata],
            ids=[self._chunk_id(doc, "summary")],
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
        embeddings = self._embedder(chunks)
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
        return metadata

    def _chunk_id(self, doc: SourceDocument, suffix: Any) -> str:
        return f"{doc.id}:{suffix}:{uuid4().hex[:8]}"

    def _namespace_for(self, doc: SourceDocument) -> str:
        if doc.source_type.startswith("youtube"):
            return self.config.collections.youtube
        if doc.source_type in {"note", "session_summary"}:
            return self.config.collections.notes
        return self.config.collections.web_articles

    def _summarize(self, text: str, doc: SourceDocument) -> Optional[str]:
        prompt = (
            "You are Argo's summarizer. Provide a concise, factual summary of the provided document. "
            "Keep it under 4 sentences."
        )
        user = f"Title: {doc.title or 'n/a'}\nURL: {doc.url or 'n/a'}\n\n{text[:4000]}"
        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=user),
        ]
        try:
            summary = self.llm_client.chat(messages, temperature=0.2, max_tokens=256)
        except Exception:  # noqa: BLE001 - summarization best-effort
            return None
        cleaned = (summary or "").strip()
        return cleaned or None


_DEFAULT_MANAGER: Optional[IngestionManager] = None


def get_default_ingestion_manager() -> IngestionManager:
    """Return a cached ingestion manager shared across tools."""

    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = IngestionManager()
    return _DEFAULT_MANAGER


__all__ = ["IngestionManager", "IngestionPolicy", "get_default_ingestion_manager"]
