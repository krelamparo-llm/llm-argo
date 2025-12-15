"""High-level memory orchestration for Argo Brain.

MemoryManager focuses on:
- Assembling context from multiple memory layers
- Extracting and storing autobiographical memories
- Querying the knowledge base

Session management and tool tracking are delegated to SessionManager and ToolTracker.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ..config import CONFIG
from ..embeddings import embed_single, embed_texts
from ..llm_client import ChatMessage, LLMClient
from ..rag import RetrievedChunk, retrieve_knowledge
from ..tools.base import ToolResult
from ..vector_store import get_vector_store, Document
from ..utils.json_helpers import extract_json_object
from .db import MemoryDB, MessageRecord, ProfileFact
from .prompts import MEMORY_WRITER_INSTRUCTIONS, format_messages_for_prompt
from .session_manager import SessionManager
from ..security import TrustLevel


@dataclass
class ContextIdentifier:
    """Lightweight reference to a memory chunk without full content."""

    chunk_id: str
    title: str
    snippet: str  # First ~150 chars
    url: Optional[str] = None
    source_type: Optional[str] = None
    relevance_score: Optional[float] = None
    timestamp: Optional[str] = None


@dataclass
class AutobiographicalChunk:
    """Semantic memory retrieved from the autobiographical store."""

    text: str
    metadata: Dict[str, str]
    chunk_id: str
    distance: Optional[float] = None


@dataclass
class MemoryContext:
    """Structured bundle of context segments for prompting."""

    short_term_messages: List[MessageRecord]
    session_summary: Optional[str]
    autobiographical_chunks: List[AutobiographicalChunk]
    rag_chunks: List[RetrievedChunk]
    web_cache_chunks: List[RetrievedChunk]
    tool_results: List[ToolResult]


class MemoryManager:
    """Retrieves and writes autobiographical memories.

    Focuses on memory-specific operations:
    - Context assembly from 8 layers
    - Autobiographical memory extraction and storage
    - Generic knowledge base queries

    Delegates to:
    - SessionManager: conversation lifecycle and summarization
    - ToolTracker: tool execution logging (handled by orchestrator)
    """

    def __init__(
        self,
        db: Optional[MemoryDB] = None,
        llm_client: Optional[LLMClient] = None,
        session_manager: Optional[SessionManager] = None,
        *,
        vector_store=None,
    ) -> None:
        self.db = db or MemoryDB()
        self.llm_client = llm_client or LLMClient()
        self.session_manager = session_manager or SessionManager(self.db, self.llm_client)
        self.config = CONFIG
        self.logger = logging.getLogger("argo_brain.memory")
        self.vector_store = vector_store or get_vector_store()

    # ---- Context Assembly ------------------------------------------------
    def get_context_for_prompt(
        self,
        session_id: str,
        user_message: str,
        tool_results: Optional[List[ToolResult]] = None,
    ) -> MemoryContext:
        """Assemble 8-layer context for the assistant prompt.

        Layers:
        1. Short-term message buffer (from SessionManager)
        2. Session summary (from SessionManager)
        3. Autobiographical memory (vector search)
        4. RAG knowledge chunks (trust-ordered)
        5. Web cache (ephemeral, TTL-filtered)
        6. Tool results (passed in)
        7-8. Profile facts and snapshots (accessed via SQLite)
        """
        mem_cfg = self.config.memory
        security_cfg = self.config.security

        # Delegate to SessionManager for conversation context
        short_term = self.session_manager.get_recent_messages(session_id)
        summary = self.session_manager.get_session_summary(session_id)
        auto_chunks = self._retrieve_autobiographical(user_message, mem_cfg.autobiographical_k)
        rag_chunks = retrieve_knowledge(
            user_message,
            top_k=mem_cfg.rag_k,
            trust_preference=(
                TrustLevel.PERSONAL_HIGH,
                TrustLevel.WEB_UNTRUSTED,
                TrustLevel.TOOL_OUTPUT,
            ),
            max_characters=security_cfg.context_char_budget,
            max_chunks=security_cfg.context_max_chunks,
        )
        web_cache_chunks = self._retrieve_web_cache(user_message)
        self.logger.info(
            "Prepared context",
            extra={
                "session_id": session_id,
                "user_preview": user_message[:200],
                "short_term": len(short_term),
                "auto_chunks": len(auto_chunks),
                "rag_chunks": len(rag_chunks),
                "web_cache_chunks": len(web_cache_chunks),
                "tool_results": len(tool_results or []),
                "has_summary": bool(summary),
                "rag_trust": self._summarize_trust(rag_chunks),
                "web_trust": self._summarize_trust(web_cache_chunks),
            },
        )
        # Deduplicate chunks by URL (Phase 1.4 refactor)
        # Priority: tool_results > web_cache > rag (freshness order)
        rag_chunks, web_cache_chunks = self._deduplicate_chunks(
            rag_chunks, web_cache_chunks, tool_results or []
        )

        return MemoryContext(
            short_term_messages=short_term,
            session_summary=summary,
            autobiographical_chunks=auto_chunks,
            rag_chunks=rag_chunks,
            web_cache_chunks=web_cache_chunks,
            tool_results=tool_results if tool_results is not None else [],
        )

    def _deduplicate_chunks(
        self,
        rag_chunks: List[RetrievedChunk],
        web_cache_chunks: List[RetrievedChunk],
        tool_results: List[ToolResult],
    ) -> Tuple[List[RetrievedChunk], List[RetrievedChunk]]:
        """Remove duplicate content across context sources.

        Deduplication priority (freshest wins):
        1. Tool results (current conversation)
        2. Web cache (recent tool outputs)
        3. RAG chunks (knowledge base)

        Uses both URL-based and content-hash deduplication.

        Args:
            rag_chunks: Chunks from knowledge base
            web_cache_chunks: Chunks from web cache
            tool_results: Tool results from current conversation

        Returns:
            Deduplicated (rag_chunks, web_cache_chunks) tuple
        """
        seen_urls: Set[str] = set()
        seen_hashes: Set[str] = set()

        # First, collect URLs and hashes from tool results (highest priority)
        for result in tool_results:
            if result.metadata:
                url = result.metadata.get("url")
                if url:
                    seen_urls.add(self._normalize_url(url))
            # Also hash content to catch duplicates without URLs
            if result.content:
                seen_hashes.add(self._content_hash(result.content))

        # Deduplicate web_cache_chunks (second priority)
        deduped_web_cache: List[RetrievedChunk] = []
        for chunk in web_cache_chunks:
            url = chunk.metadata.get("url") if chunk.metadata else None
            normalized_url = self._normalize_url(url) if url else None
            content_hash = self._content_hash(chunk.text)

            if normalized_url and normalized_url in seen_urls:
                self.logger.debug(f"Dedup: skipping web_cache chunk (URL duplicate): {url[:60]}...")
                continue
            if content_hash in seen_hashes:
                self.logger.debug("Dedup: skipping web_cache chunk (content hash duplicate)")
                continue

            # Keep this chunk and mark as seen
            if normalized_url:
                seen_urls.add(normalized_url)
            seen_hashes.add(content_hash)
            deduped_web_cache.append(chunk)

        # Deduplicate rag_chunks (lowest priority)
        deduped_rag: List[RetrievedChunk] = []
        for chunk in rag_chunks:
            url = chunk.metadata.get("url") if chunk.metadata else None
            normalized_url = self._normalize_url(url) if url else None
            content_hash = self._content_hash(chunk.text)

            if normalized_url and normalized_url in seen_urls:
                self.logger.debug(f"Dedup: skipping RAG chunk (URL duplicate): {url[:60]}...")
                continue
            if content_hash in seen_hashes:
                self.logger.debug("Dedup: skipping RAG chunk (content hash duplicate)")
                continue

            # Keep this chunk and mark as seen
            if normalized_url:
                seen_urls.add(normalized_url)
            seen_hashes.add(content_hash)
            deduped_rag.append(chunk)

        # Log deduplication stats
        rag_removed = len(rag_chunks) - len(deduped_rag)
        web_removed = len(web_cache_chunks) - len(deduped_web_cache)
        if rag_removed > 0 or web_removed > 0:
            self.logger.info(
                "Context deduplication",
                extra={
                    "rag_removed": rag_removed,
                    "web_cache_removed": web_removed,
                    "rag_kept": len(deduped_rag),
                    "web_cache_kept": len(deduped_web_cache),
                },
            )

        return deduped_rag, deduped_web_cache

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication comparison.

        Removes trailing slashes, fragments, and normalizes case.
        """
        if not url:
            return ""
        # Remove fragment
        url = url.split("#")[0]
        # Remove trailing slash
        url = url.rstrip("/")
        # Lowercase for comparison
        return url.lower()

    def _content_hash(self, text: str) -> str:
        """Generate content hash for deduplication.

        Normalizes whitespace and case before hashing.
        """
        if not text:
            return ""
        # Normalize: lowercase, collapse whitespace
        normalized = " ".join(text.lower().split())
        # Take first 1000 chars to avoid hashing huge content
        normalized = normalized[:1000]
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def _retrieve_web_cache(self, query: str) -> List[RetrievedChunk]:
        mem_cfg = self.config.memory
        filters = None
        if mem_cfg.web_cache_ttl_days > 0:
            cutoff = int(time.time()) - mem_cfg.web_cache_ttl_days * 86400
            filters = {"fetched_at": {"$gt": cutoff}}
        security_cfg = self.config.security
        return retrieve_knowledge(
            query,
            top_k=max(3, mem_cfg.rag_k // 2),
            filters=filters,
            collection_name=self.config.collections.web_cache,
            max_characters=security_cfg.context_char_budget,
            max_chunks=max(3, min(mem_cfg.rag_k, security_cfg.context_max_chunks)),
        )

    def _retrieve_autobiographical(self, query: str, top_k: int) -> List[AutobiographicalChunk]:
        if not query.strip():
            return []
        embedding_vec = embed_single(query)
        if not embedding_vec:
            return []
        query_embedding = np.array(embedding_vec, dtype=float)
        documents = self.vector_store.query(
            namespace=self.config.collections.autobiographical,
            query_embedding=query_embedding,
            k=top_k,
        )
        chunks: List[AutobiographicalChunk] = []
        for doc in documents:
            chunks.append(
                AutobiographicalChunk(
                    text=doc.text,
                    metadata=doc.metadata or {},
                    chunk_id=doc.id,
                    distance=doc.score,
                )
            )
        return chunks

    # ---- Memory Extraction -----------------------------------------------
    def extract_and_store_memories(
        self,
        session_id: str,
        recent_turns: List[MessageRecord],
    ) -> None:
        """Extract autobiographical facts from recent conversation and store them.

        This is called after each interaction to extract long-lived facts about
        the user from the conversation.
        """
        if not recent_turns:
            return

        start = time.perf_counter()
        memories = self._run_memory_writer(recent_turns)
        if memories:
            self._store_autobiographical_memories(memories)
            self.logger.info(
                "Stored autobiographical memories",
                extra={"session_id": session_id, "items": len(memories)},
            )
        elapsed = time.perf_counter() - start
        self.logger.debug(
            "Memory extraction completed",
            extra={"session_id": session_id, "elapsed_ms": round(elapsed * 1000, 2)},
        )

    def _run_memory_writer(
        self,
        recent_turns: List[MessageRecord],
    ) -> List[Dict[str, str]]:
        """Use LLM to extract memories from recent conversation."""
        if not recent_turns:
            return []

        # Format recent turns as transcript
        transcript = format_messages_for_prompt(recent_turns)
        prompt_body = f"Recent conversation:\n{transcript}\n\nExtract long-lived facts about the user."

        messages = [
            ChatMessage(role="system", content=MEMORY_WRITER_INSTRUCTIONS),
            ChatMessage(role="user", content=prompt_body),
        ]

        try:
            raw_response = self.llm_client.chat(messages, temperature=0.1, max_tokens=256)
        except Exception as e:
            self.logger.error("Memory writer LLM call failed", exc_info=True, extra={"error": str(e)})
            return []

        try:
            data = extract_json_object(raw_response)
        except (ValueError, json.JSONDecodeError) as e:
            self.logger.warning("Memory writer returned invalid JSON", extra={"error": str(e)})
            return []

        if not isinstance(data, dict):
            self.logger.warning("Memory writer returned non-dict")
            return []

        memories = data.get("memories", [])
        if not isinstance(memories, list) or not memories:
            return []

        # Extract session_id from first turn (all should have same session_id)
        session_id = recent_turns[0].session_id if recent_turns else "unknown"

        # Build memory records
        memory_records = []
        for memory in memories:
            text = (memory or {}).get("text", "").strip()
            mem_type = (memory or {}).get("type", "fact")
            if not text:
                continue

            # Store in SQLite profile_facts
            self.db.add_profile_fact(
                text,
                user_id="default",
                source_session_id=session_id,
            )

            memory_records.append({
                "text": text,
                "metadata": {
                    "session_id": session_id,
                    "type": mem_type,
                    "source_type": "conversation",
                }
            })

        return memory_records

    def _store_autobiographical_memories(self, memory_records: List[Dict[str, str]]) -> None:
        """Store extracted memories in vector store."""
        if not memory_records:
            return

        texts = [record["text"] for record in memory_records]
        metadatas = [record["metadata"] for record in memory_records]

        embeddings = np.array(embed_texts(texts), dtype=float)
        ids = [f"auto:{time.time()}:{idx}" for idx in range(len(texts))]

        self.vector_store.add(
            namespace=self.config.collections.autobiographical_memory,
            ids=ids,
            texts=texts,
            embeddings=embeddings,
            metadatas=[{**metadata, "trust_level": TrustLevel.PERSONAL_HIGH.value} for metadata in metadatas],
        )

    # ---- Profile facts ---------------------------------------------------
    def list_profile_facts(self, active_only: bool = True) -> List[ProfileFact]:
        """List stored profile facts from SQLite."""
        return self.db.list_profile_facts(active_only=active_only)

    def set_fact_active(self, fact_id: int, is_active: bool) -> None:
        """Toggle visibility of a profile fact."""
        self.db.set_profile_fact_active(fact_id, is_active)

    # ---- Generic Memory Query --------------------------------------------
    def query_memory(
        self,
        query: str,
        *,
        namespace: Optional[str] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:  # Returns Document objects from vector store
        """Retrieve chunks from vector store (used by MemoryQueryTool).

        This is a general-purpose query interface that tools can use to search
        the knowledge base.
        """
        from ..vector_store import Document

        target_namespace = namespace or self.config.collections.web_articles
        embedding_vec = embed_single(query)
        if not embedding_vec:
            return []

        query_embedding = np.array(embedding_vec, dtype=float)
        documents = self.vector_store.query(
            namespace=target_namespace,
            query_embedding=query_embedding,
            k=top_k,
            filters=filters,
        )

        # Ensure all documents have trust metadata
        for doc in documents:
            meta = doc.metadata or {}
            if "trust_level" not in meta:
                meta["trust_level"] = TrustLevel.WEB_UNTRUSTED.value

        return documents

    def _summarize_trust(self, chunks: List[RetrievedChunk]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for chunk in chunks:
            trust = chunk.metadata.get("trust_level", "unknown")
            counts[trust] = counts.get(trust, 0) + 1
        return counts

    # ---- Just-In-Time Context Retrieval (Phase 2) ---------------------------
    def get_context_identifiers(
        self,
        query: str,
        *,
        max_identifiers: int = 10,
        namespace: Optional[str] = None,
    ) -> List[ContextIdentifier]:
        """Return lightweight identifiers instead of full content.

        This implements the 'just-in-time context retrieval' pattern from
        Anthropic's context engineering guidance. Instead of loading full
        content upfront, we return identifiers that can be retrieved on demand.

        Args:
            query: Search query for semantic matching
            max_identifiers: Maximum number of identifiers to return
            namespace: Optional vector store namespace to query

        Returns:
            List of ContextIdentifier with snippets and metadata
        """
        target_namespace = namespace or self.config.collections.rag
        embedding_vec = embed_single(query)
        if not embedding_vec:
            return []

        query_embedding = np.array(embedding_vec, dtype=float)
        documents = self.vector_store.query(
            namespace=target_namespace,
            query_embedding=query_embedding,
            k=max_identifiers,
        )

        identifiers: List[ContextIdentifier] = []
        for doc in documents:
            metadata = doc.metadata or {}
            text = doc.text or ""

            # Extract title from metadata or first line of text
            title = metadata.get("title")
            if not title:
                first_line = text.split("\n")[0][:80] if text else "Untitled"
                title = first_line if first_line else "Untitled"

            # Create snippet (first ~150 chars)
            snippet = text[:150].strip()
            if len(text) > 150:
                snippet += "..."

            identifiers.append(
                ContextIdentifier(
                    chunk_id=doc.id,
                    title=title,
                    snippet=snippet,
                    url=metadata.get("url"),
                    source_type=metadata.get("source_type"),
                    relevance_score=doc.score,
                    timestamp=metadata.get("timestamp") or metadata.get("fetched_at"),
                )
            )

        self.logger.info(
            "Retrieved context identifiers",
            extra={
                "query_preview": query[:100],
                "namespace": target_namespace,
                "count": len(identifiers),
            },
        )
        return identifiers

    def retrieve_chunk_by_id(
        self,
        chunk_id: str,
        *,
        namespace: Optional[str] = None,
    ) -> Optional[str]:
        """Retrieve full content for a specific chunk by ID.

        This is the second part of just-in-time retrieval - only fetch
        full content when the model explicitly requests it.

        Args:
            chunk_id: The unique identifier for the chunk
            namespace: Optional namespace (defaults to RAG collection)

        Returns:
            Full text content of the chunk, or None if not found
        """
        target_namespace = namespace or self.config.collections.rag

        # Try to get document directly by ID
        try:
            doc = self.vector_store.get_by_id(
                namespace=target_namespace,
                doc_id=chunk_id,
            )
            if doc:
                self.logger.info(
                    "Retrieved chunk by ID",
                    extra={
                        "chunk_id": chunk_id,
                        "namespace": target_namespace,
                        "content_length": len(doc.text) if doc.text else 0,
                    },
                )
                return doc.text
        except Exception as exc:
            self.logger.warning(
                "Failed to retrieve chunk by ID",
                extra={"chunk_id": chunk_id, "error": str(exc)},
            )

        return None

    def get_lightweight_context(
        self,
        session_id: str,
        user_message: str,
        *,
        max_identifiers: int = 8,
    ) -> Dict[str, Any]:
        """Get lightweight context with identifiers instead of full content.

        This is an alternative to get_context_for_prompt() that returns
        identifiers for just-in-time retrieval.

        Returns:
            Dict with:
            - short_term_messages: Recent conversation (same as before)
            - session_summary: Summary text (same as before)
            - memory_identifiers: List of ContextIdentifier objects
            - tool_instructions: Instructions for using retrieve_context tool
        """
        mem_cfg = self.config.memory

        # Get conversation context (these are small, keep as-is)
        short_term = self.session_manager.get_recent_messages(session_id)
        summary = self.session_manager.get_session_summary(session_id)

        # Get identifiers instead of full chunks
        identifiers = self.get_context_identifiers(
            user_message,
            max_identifiers=max_identifiers,
        )

        self.logger.info(
            "Prepared lightweight context",
            extra={
                "session_id": session_id,
                "short_term": len(short_term),
                "identifiers": len(identifiers),
                "has_summary": bool(summary),
            },
        )

        return {
            "short_term_messages": short_term,
            "session_summary": summary,
            "memory_identifiers": identifiers,
            "tool_instructions": (
                "To get full content for any memory chunk, use:\n"
                "retrieve_context(chunk_id=\"<id>\")\n"
                "Only retrieve chunks you actually need to cite or analyze in detail."
            ),
        }
