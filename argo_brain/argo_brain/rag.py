"""Core RAG utilities shared across the Argo Brain scripts."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

import numpy as np
import requests
import trafilatura

from .config import CONFIG
from .embeddings import embed_single, embed_texts
from .llm_client import ChatMessage, LLMClient
from .vector_store import get_vector_store

_VECTOR_STORE = get_vector_store()


@dataclass
class RetrievedChunk:
    """Represents a chunk of knowledge retrieved from Chroma."""

    text: str
    metadata: Dict[str, Any]
    chunk_id: str
    distance: Optional[float] = None


def split_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks."""

    cleaned = text.strip()
    if not cleaned:
        return []
    chunks: List[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(cleaned[start:end])
        if end >= length:
            break
        start = max(0, end - overlap)
    return chunks


def ingest_text(
    text: str,
    source_id: str,
    source_type: str,
    url: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
    *,
    collection_name: Optional[str] = None,
) -> None:
    """Chunk text and insert it into the RAG Chroma collection."""

    chunks = split_text(text)
    if not chunks:
        raise ValueError("No usable text found to ingest.")

    embeddings_list = embed_texts(chunks)
    embeddings = np.array(embeddings_list, dtype=float)
    timestamp = int(time.time())
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []
    for idx, chunk in enumerate(chunks):
        metadata: Dict[str, Any] = {
            "source_id": source_id,
            "source_type": source_type,
            "chunk_index": idx,
            "ingested_ts": timestamp,
        }
        if url:
            metadata["url"] = url
        if extra_meta:
            metadata.update(extra_meta)
        metadatas.append(metadata)
        ids.append(f"{source_id}:{timestamp}:{idx}:{uuid4().hex[:8]}")

    target_collection = collection_name or CONFIG.collections.rag
    _VECTOR_STORE.add(
        namespace=target_collection,
        ids=ids,
        texts=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )


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
    """Store live web browsing output into the dedicated web cache collection."""

    metadata = {
        "url": url,
        "source_type": "live_web",
        "query_id": query_id,
        "fetched_at": fetched_at or int(time.time()),
    }
    if extra_meta:
        metadata.update(extra_meta)
    ingest_text(
        text=content,
        source_id=source_id,
        source_type="live_web",
        url=url,
        extra_meta=metadata,
        collection_name=CONFIG.collections.web_cache,
    )


def retrieve_knowledge(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    *,
    collection_name: Optional[str] = None,
) -> List[RetrievedChunk]:
    """Retrieve semantically similar chunks for a query."""

    target_collection = collection_name or CONFIG.collections.rag
    embedding_vec = embed_single(query)
    if not embedding_vec:
        return []
    query_embedding = np.array(embedding_vec, dtype=float)
    documents = _VECTOR_STORE.query(
        namespace=target_collection,
        query_embedding=query_embedding,
        k=top_k,
        filters=filters,
    )
    chunks: List[RetrievedChunk] = []
    for doc in documents:
        chunks.append(
            RetrievedChunk(
                text=doc.text,
                metadata=doc.metadata or {},
                chunk_id=doc.id,
                distance=doc.score,
            )
        )
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
