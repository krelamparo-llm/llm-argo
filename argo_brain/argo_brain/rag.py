"""Core RAG utilities shared across the Argo Brain scripts."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
import numpy as np
import requests
import trafilatura

from .config import CONFIG
from .core.memory.document import SourceDocument
from .core.memory.ingestion import get_default_ingestion_manager
from .core.memory.decay import apply_decay_scoring, filter_expired
from .embeddings import embed_single
from .llm_client import ChatMessage, LLMClient
from .vector_store import get_vector_store
from .security import TrustLevel, ensure_trust_metadata, flatten_namespaces, trust_level_for_source
from .security.injection import is_suspicious_text

_VECTOR_STORE = get_vector_store()
_INGESTION_MANAGER = get_default_ingestion_manager()


@dataclass
class RetrievedChunk:
    """Represents a chunk of knowledge retrieved from Chroma."""

    text: str
    metadata: Dict[str, Any]
    chunk_id: str
    distance: Optional[float] = None


def ingest_text(
    text: str,
    source_id: str,
    source_type: str,
    url: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
    *,
    collection_name: Optional[str] = None,
) -> None:
    """Ingest text into appropriate namespace based on source_type.

    This is the main entry point for archival ingestion (browser history,
    YouTube transcripts, explicit saves). Content is stored as full chunks.
    """
    doc = SourceDocument(
        id=source_id,
        source_type=source_type,
        raw_text=text,
        cleaned_text=text,
        url=url,
        metadata=extra_meta or {},
    )
    _INGESTION_MANAGER.ingest_document(doc, ephemeral=False)


def _fetch_html(url: str, timeout: int = 25) -> str:
    headers = {"User-Agent": "ArgoBrain/1.0 (+https://argo-brain.local)"}
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def ingest_url(url: str) -> None:
    """Download a URL, extract its article text, and ingest it."""

    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Only http(s) URLs are supported: {url}")
    html = _fetch_html(url)
    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not extracted:
        raise RuntimeError(f"Could not extract main content from {url}")
    ingest_text(text=extracted, source_id=url, source_type="web_page", url=url)


def ingest_web_result(
    content: str,
    *,
    source_id: str,
    url: str,
    query_id: Optional[str] = None,
    fetched_at: Optional[int] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Store live web content in ephemeral cache with TTL.

    Used during deep research for temporary web fetches that should expire.
    """
    metadata = {
        "url": url,
        "source_type": "live_web",
        "query_id": query_id,
        "fetched_at": fetched_at or int(time.time()),
        "trust_level": TrustLevel.WEB_UNTRUSTED.value,
    }
    if extra_meta:
        metadata.update(extra_meta)
    doc = SourceDocument(
        id=source_id,
        source_type="live_web",
        raw_text=content,
        cleaned_text=content,
        url=url,
        metadata=metadata,
    )
    _INGESTION_MANAGER.ingest_document(doc, ephemeral=True)


def retrieve_knowledge(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    *,
    collection_name: Optional[str] = None,
    namespaces: Optional[Sequence[str]] = None,
    trust_preference: Optional[Sequence[TrustLevel]] = None,
    max_characters: Optional[int] = None,
    max_chunks: Optional[int] = None,
) -> List[RetrievedChunk]:
    """Retrieve semantically similar chunks for a query within configured limits."""

    security_cfg = CONFIG.security
    embedding_vec = embed_single(query)
    if not embedding_vec:
        return []
    query_embedding = np.array(embedding_vec, dtype=float)

    namespace_order: List[str]
    if namespaces:
        namespace_order = [ns for ns in namespaces if ns]
    elif trust_preference:
        namespace_order = flatten_namespaces(trust_preference)
    elif collection_name:
        namespace_order = [collection_name]
    else:
        namespace_order = [CONFIG.collections.rag]
    if not namespace_order:
        namespace_order = [CONFIG.collections.rag]

    chunk_limit = top_k
    if max_chunks is not None:
        chunk_limit = min(chunk_limit, max_chunks)
    if security_cfg.context_max_chunks:
        chunk_limit = min(chunk_limit, security_cfg.context_max_chunks)
    chunk_limit = max(1, chunk_limit)
    char_budget = max_characters or security_cfg.context_char_budget or None
    total_chars = 0
    chunks: List[RetrievedChunk] = []
    for namespace in namespace_order:
        if len(chunks) >= chunk_limit:
            break
        remaining = chunk_limit - len(chunks)
        documents = _VECTOR_STORE.query(
            namespace=namespace,
            query_embedding=query_embedding,
            k=remaining,
            filters=filters,
        )

        # Apply decay scoring and TTL filtering
        documents = filter_expired(documents, namespace)
        documents = apply_decay_scoring(documents, namespace)

        for doc in documents:
            text = (doc.text or "").strip()
            if not text:
                continue
            metadata = ensure_trust_metadata(doc.metadata or {}, trust_level_for_source(doc.metadata.get("source_type")))
            metadata.setdefault("namespace", namespace)
            if security_cfg.enable_injection_filter and is_suspicious_text(text, security_cfg.suspicious_phrases):
                continue
            projected_chars = total_chars + len(text)
            if char_budget and projected_chars > char_budget and chunks:
                continue
            chunks.append(
                RetrievedChunk(
                    text=text,
                    metadata=metadata,
                    chunk_id=doc.id,
                    distance=doc.score,
                )
            )
            total_chars = projected_chars
            if len(chunks) >= chunk_limit:
                break
    return chunks


def ask_with_context(question: str, context_chunks: Sequence[str], llm_client: LLMClient) -> str:
    """Ask the local LLM to answer using explicit context chunks."""

    if not context_chunks:
        raise ValueError("No context provided to the LLM.")
    context_block = "\n\n".join(f"[Chunk {idx+1}]\n{chunk}" for idx, chunk in enumerate(context_chunks))
    system_prompt = (
        "You are Argo, a grounded assistant. Only answer using the supplied context. "
        "If the answer is not present, respond that you do not know."
    )
    user_prompt = (
        "Context:\n"
        f"{context_block}\n\n"
        f"Question: {question}\n"
        "Explain your reasoning briefly and cite chunks like [Chunk 1]."
    )
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
    return llm_client.chat(messages)


def answer_question(question: str, k: int = 8, llm_client: Optional[LLMClient] = None) -> str:
    """Full RAG loop that retrieves context and queries the LLM."""

    chunks = retrieve_knowledge(question, top_k=k)
    if not chunks:
        return "No context found in the knowledge base yet."
    client = llm_client or LLMClient()
    return ask_with_context(question, [chunk.text for chunk in chunks], client)
