"""
Core Retrieval-Augmented Generation (RAG) utilities for the Argo Brain project.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests
import trafilatura
from chromadb import PersistentClient
from chromadb.api.models.Collection import Collection
from requests import Response
from sentence_transformers import SentenceTransformer

STORAGE_ROOT = Path("/mnt/d/llm/argo_brain")
VECTOR_DB_DIR = STORAGE_ROOT / "vectordb"
COLLECTION_NAME = "argo_brain_memory"
LLM_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"

_CHROMA_CLIENT: Optional[PersistentClient] = None
_CHROMA_COLLECTION: Optional[Collection] = None
_EMBED_MODEL: Optional[SentenceTransformer] = None


def _get_collection() -> Collection:
    """Return a lazily initialized Chroma collection stored on /mnt/d."""

    global _CHROMA_CLIENT, _CHROMA_COLLECTION
    if _CHROMA_CLIENT is None:
        VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        _CHROMA_CLIENT = PersistentClient(path=str(VECTOR_DB_DIR))
    if _CHROMA_COLLECTION is None:
        _CHROMA_COLLECTION = _CHROMA_CLIENT.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Argo Brain personal knowledge base"},
        )
    return _CHROMA_COLLECTION


def _get_embedder() -> SentenceTransformer:
    """Return the sentence-transformers model used for embeddings."""

    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("BAAI/bge-m3")
    return _EMBED_MODEL


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed a list of strings using the configured sentence transformer.

    Args:
        texts: Plain-text strings to embed.

    Returns:
        A list of embedding vectors (each vector is a list of floats).
    """

    if not texts:
        return []
    model = _get_embedder()
    embeddings = model.encode(texts, batch_size=8, normalize_embeddings=True)
    return [vec.tolist() if hasattr(vec, "tolist") else list(vec) for vec in embeddings]


def split_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    """
    Split a long string into overlapping chunks for RAG ingestion.

    Args:
        text: Input text to chunk.
        chunk_size: Target size of each chunk measured in characters.
        overlap: Number of characters to overlap between successive chunks.

    Returns:
        List of chunked strings.
    """

    cleaned = text.strip()
    if not cleaned:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
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
    """
    Ingest arbitrary text into Chroma with metadata describing the source.

    Args:
        text: Raw content to store.
        source_id: Identifier for the logical source document.
        source_type: Category of the source (e.g., "web_page", "youtube_transcript").
        url: Optional canonical URL associated with the text.
        extra_meta: Additional metadata to persist alongside each chunk.
    """

    chunks = split_text(text)
    if not chunks:
        raise ValueError("No usable text found to ingest.")

    embeddings = embed_texts(chunks)
    collection = _get_collection()
    timestamp = int(time.time())
    metadatas = []
    ids = []
    for idx, chunk in enumerate(chunks):
        meta: Dict[str, Any] = {
            "source_id": source_id,
            "source_type": source_type,
            "chunk_index": idx,
            "ingested_ts": timestamp,
        }
        if url:
            meta["url"] = url
        if extra_meta:
            meta.update(extra_meta)
        metadatas.append(meta)
        ids.append(f"{source_id}:{timestamp}:{idx}:{uuid4().hex[:8]}")

    collection.upsert(
        ids=ids,
        documents=chunks,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def _fetch_html(url: str, timeout: int = 20) -> str:
    """Download the raw HTML for a URL."""

    headers = {
        "User-Agent": "ArgoBrain/1.0 (+https://example.com)",
    }
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def ingest_url(url: str) -> None:
    """
    Fetch a URL, extract the main article text, and store it in the vector DB.

    Args:
        url: HTTP(S) URL to scrape and ingest.
    """

    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Only http(s) URLs are supported: {url}")

    html = _fetch_html(url)
    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not extracted:
        raise RuntimeError(f"Could not extract main content from {url}")
    ingest_text(
        text=extracted,
        source_id=url,
        source_type="web_page",
        url=url,
    )


def retrieve(query: str, k: int = 8) -> Dict[str, Any]:
    """
    Retrieve the top-k relevant chunks for a natural language query.

    Args:
        query: Natural language string describing the information need.
        k: Number of results to return.

    Returns:
        A dictionary mirroring the Chroma query response.
    """

    collection = _get_collection()
    return collection.query(
        query_texts=[query],
        n_results=k,
    )


def _call_local_llm(messages: List[Dict[str, str]]) -> str:
    """Send a chat completion request to the llama-server endpoint."""

    payload = {
        "model": "local-llm",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 512,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer local-token",
    }
    response: Response = requests.post(
        LLM_ENDPOINT, headers=headers, data=json.dumps(payload), timeout=60
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"llama-server returned {response.status_code}: {response.text}"
        )
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected LLM response: {data}") from exc


def ask_argo_with_context(question: str, context_chunks: List[str]) -> str:
    """
    Ask the local LLM to answer a question using supplied context snippets.

    Args:
        question: The user's natural language question.
        context_chunks: Relevant snippets retrieved from the vector DB.

    Returns:
        Answer string returned by the LLM.
    """

    if not context_chunks:
        raise ValueError("No context provided to the LLM.")

    context_block = "\n\n".join(
        f"[Chunk {idx+1}]\n{chunk}" for idx, chunk in enumerate(context_chunks)
    )
    system_prompt = (
        "You are Argo, a personal RAG assistant. Only use the provided context "
        "chunks to answer. If the answer is not present, say you do not know."
    )
    user_prompt = (
        "Context:\n"
        f"{context_block}\n\n"
        f"Question: {question}\n"
        "Explain your reasoning briefly and cite chunks like [Chunk 1]."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return _call_local_llm(messages)


def rag_answer(question: str, k: int = 8) -> str:
    """
    Run the full RAG loop: retrieve context and ask the LLM for an answer.

    Args:
        question: Natural language question to pose.
        k: Number of chunks to retrieve from the vector DB.

    Returns:
        String answer produced by the LLM.
    """

    results = retrieve(question, k=k)
    documents = results.get("documents", [[]])[0]
    if not documents:
        return "No context found in the knowledge base yet."
    return ask_argo_with_context(question, documents)


def _looks_like_url(text: str) -> bool:
    """Return True when the input resembles an http(s) URL."""

    lowered = text.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _main(argv: List[str]) -> None:
    """CLI entry point to ingest a URL or ask a question."""

    if len(argv) < 2:
        print(
            "Usage: python3 rag_core.py <url|question>\n"
            " - Provide an http(s) URL to ingest it.\n"
            " - Provide a natural language question for a RAG answer."
        )
        return
    query = " ".join(argv[1:]).strip()
    if _looks_like_url(query):
        ingest_url(query)
        print(f"Ingested URL: {query}")
    else:
        print(rag_answer(query))


if __name__ == "__main__":
    _main(sys.argv)
