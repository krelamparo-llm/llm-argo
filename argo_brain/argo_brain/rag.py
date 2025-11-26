"""Core RAG utilities shared across the Argo Brain scripts."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

import requests
import trafilatura
from chromadb import PersistentClient
from chromadb.api.models.Collection import Collection

from .config import CONFIG
from .embeddings import embed_texts
from .llm_client import ChatMessage, LLMClient

_CHROMA_CLIENT: Optional[PersistentClient] = None
_RAG_COLLECTION: Optional[Collection] = None


@dataclass
class RetrievedChunk:
    """Represents a chunk of knowledge retrieved from Chroma."""

    text: str
    metadata: Dict[str, Any]
    chunk_id: str
    distance: Optional[float] = None


def _get_collection() -> Collection:
    """Return (creating if necessary) the primary RAG Chroma collection."""

    global _CHROMA_CLIENT, _RAG_COLLECTION
    paths = CONFIG.paths
    if _CHROMA_CLIENT is None:
        paths.vector_db_path.mkdir(parents=True, exist_ok=True)
        _CHROMA_CLIENT = PersistentClient(path=str(paths.vector_db_path))
    if _RAG_COLLECTION is None:
        _RAG_COLLECTION = _CHROMA_CLIENT.get_or_create_collection(
            name=CONFIG.collections.rag,
            metadata={"description": "Argo Brain web/article/YouTube knowledge"},
        )
    return _RAG_COLLECTION


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
) -> None:
    """Chunk text and insert it into the RAG Chroma collection."""

    chunks = split_text(text)
    if not chunks:
        raise ValueError("No usable text found to ingest.")

    embeddings = embed_texts(chunks)
    collection = _get_collection()
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

    collection.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)


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


def retrieve_knowledge(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> List[RetrievedChunk]:
    """Retrieve semantically similar chunks for a query."""

    collection = _get_collection()
    response = collection.query(query_texts=[query], n_results=top_k, where=filters)
    documents = response.get("documents", [[]])[0]
    metadatas = response.get("metadatas", [[]])[0]
    ids = response.get("ids", [[]])[0]
    distances = response.get("distances", [[]])[0]

    chunks: List[RetrievedChunk] = []
    for doc, meta, chunk_id, dist in zip(documents, metadatas, ids, distances):
        chunks.append(
            RetrievedChunk(
                text=doc,
                metadata=meta or {},
                chunk_id=chunk_id,
                distance=dist,
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
