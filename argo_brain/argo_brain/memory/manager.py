"""High-level memory orchestration for Argo Brain."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np

from ..config import CONFIG
from ..core.memory.document import SourceDocument
from ..core.memory.ingestion import IngestionManager
from ..core.memory.session import SessionMode
from ..embeddings import embed_single, embed_texts
from ..llm_client import ChatMessage, LLMClient
from ..rag import RetrievedChunk, retrieve_knowledge
from ..tools.base import ToolRequest, ToolResult
from ..vector_store import get_vector_store
from .db import MemoryDB, MessageRecord, ProfileFact, ToolRunRecord
from .prompts import (
    MEMORY_WRITER_INSTRUCTIONS,
    SESSION_SUMMARY_INSTRUCTIONS,
    format_messages_for_prompt,
)


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
    """Coordinates SQLite, Chroma, and LLM prompts for memory."""

    def __init__(
        self,
        db: Optional[MemoryDB] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.db = db or MemoryDB()
        self.llm_client = llm_client or LLMClient()
        self.config = CONFIG
        self.logger = logging.getLogger("argo_brain.memory")
        self.vector_store = get_vector_store()
        self.ingestion_manager = IngestionManager(
            vector_store=self.vector_store,
            llm_client=self.llm_client,
        )

    # ---- Session helpers -------------------------------------------------
    def ensure_session(self, session_id: str) -> None:
        self.db.ensure_session(session_id)

    # ---- Retrieval -------------------------------------------------------
    def get_context_for_prompt(
        self,
        session_id: str,
        user_message: str,
        tool_results: Optional[List[ToolResult]] = None,
    ) -> MemoryContext:
        """Return layered context for the assistant prompt."""

        mem_cfg = self.config.memory
        short_term = self.db.get_recent_messages(session_id, mem_cfg.short_term_window)
        summary = self.db.get_session_summary(session_id)
        auto_chunks = self._retrieve_autobiographical(user_message, mem_cfg.autobiographical_k)
        rag_chunks = retrieve_knowledge(
            user_message,
            top_k=mem_cfg.rag_k,
            collection_name=self.config.collections.rag,
        )
        web_cache_chunks = self._retrieve_web_cache(user_message)
        self.logger.info(
            "Prepared context",
            extra={
                "session_id": session_id,
                "short_term": len(short_term),
                "auto_chunks": len(auto_chunks),
                "rag_chunks": len(rag_chunks),
                "web_cache_chunks": len(web_cache_chunks),
                "tool_results": len(tool_results or []),
                "has_summary": bool(summary),
            },
        )
        return MemoryContext(
            short_term_messages=short_term,
            session_summary=summary,
            autobiographical_chunks=auto_chunks,
            rag_chunks=rag_chunks,
            web_cache_chunks=web_cache_chunks,
            tool_results=tool_results if tool_results is not None else [],
        )

    def _retrieve_web_cache(self, query: str) -> List[RetrievedChunk]:
        mem_cfg = self.config.memory
        filters = None
        if mem_cfg.web_cache_ttl_days > 0:
            cutoff = int(time.time()) - mem_cfg.web_cache_ttl_days * 86400
            filters = {"fetched_at": {"$gt": cutoff}}
        return retrieve_knowledge(
            query,
            top_k=max(3, mem_cfg.rag_k // 2),
            filters=filters,
            collection_name=self.config.collections.web_cache,
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

    def get_session_summary(self, session_id: str) -> Optional[str]:
        """Expose the latest summary for CLI inspection."""

        return self.db.get_session_summary(session_id)

    # ---- Persistence -----------------------------------------------------
    def record_interaction(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Persist the latest turn and trigger summary + memory updates."""

        start = time.perf_counter()
        self.db.add_message(session_id, "user", user_message)
        self.db.add_message(session_id, "assistant", assistant_response)
        summary = self._maybe_update_summary(session_id)
        self._run_memory_writer(session_id, user_message, assistant_response, summary)
        elapsed = time.perf_counter() - start
        self.logger.info(
            "Recorded interaction",
            extra={"session_id": session_id, "elapsed_ms": round(elapsed * 1000, 2)},
        )

    # ---- Summaries -------------------------------------------------------
    def _maybe_update_summary(self, session_id: str) -> Optional[str]:
        mem_cfg = self.config.memory
        total_messages = self.db.count_messages(session_id)
        existing_summary = self.db.get_session_summary(session_id)
        needs_summary = existing_summary is None or (total_messages % mem_cfg.summary_interval == 0)
        if not needs_summary:
            return existing_summary
        history = self.db.get_all_messages(session_id, limit=mem_cfg.summary_history_limit)
        if not history:
            return existing_summary
        conversation_text = format_messages_for_prompt(history)
        prompt_body = (
            f"Existing summary (may be empty):\n{existing_summary or 'None'}\n\n"
            f"Recent conversation:\n{conversation_text}\n\nUpdate the summary."
        )
        messages = [
            ChatMessage(role="system", content=SESSION_SUMMARY_INSTRUCTIONS),
            ChatMessage(role="user", content=prompt_body),
        ]
        summary = self.llm_client.chat(messages, temperature=0.1, max_tokens=256)
        snapshot_interval = mem_cfg.summary_snapshot_interval
        if (
            existing_summary
            and snapshot_interval > 0
            and total_messages % snapshot_interval == 0
        ):
            self.db.add_summary_snapshot(session_id, existing_summary)
            self.logger.debug(
                "Archived summary snapshot",
                extra={"session_id": session_id, "messages": total_messages},
            )
        self.db.upsert_session_summary(session_id, summary)
        self.logger.debug("Session summary updated", extra={"session_id": session_id})
        return summary

    # ---- Memory writer ---------------------------------------------------
    def _run_memory_writer(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        session_summary: Optional[str],
    ) -> None:
        summary_text = session_summary or self.db.get_session_summary(session_id) or "None yet."
        prompt_body = (
            f"Session summary:\n{summary_text}\n\n"
            "Latest exchange:\n"
            f"User: {user_message}\n"
            f"Assistant: {assistant_response}\n"
            "Remember only reusable facts."
        )
        messages = [
            ChatMessage(role="system", content=MEMORY_WRITER_INSTRUCTIONS),
            ChatMessage(role="user", content=prompt_body),
        ]
        raw_response = self.llm_client.chat(messages, temperature=0.1, max_tokens=256)
        try:
            data = json.loads(raw_response)
        except json.JSONDecodeError:
            self.logger.warning("Memory writer returned non-JSON response")
            return
        memories = data.get("memories", [])
        if not isinstance(memories, list) or not memories:
            return
        texts = []
        metadatas = []
        for memory in memories:
            text = (memory or {}).get("text", "").strip()
            mem_type = (memory or {}).get("type", "fact")
            if not text:
                continue
            self.db.add_profile_fact(
                text,
                user_id="default",
                source_session_id=session_id,
            )
            texts.append(text)
            metadatas.append(
                {
                    "session_id": session_id,
                    "type": mem_type,
                    "source_type": "conversation",
                }
            )
        if texts:
            self._store_autobiographical_memories(texts, metadatas)
            self.logger.info(
                "Stored autobiographical memories",
                extra={"session_id": session_id, "items": len(texts)},
            )

    def _store_autobiographical_memories(self, texts: List[str], metadatas: List[Dict[str, str]]) -> None:
        embeddings = np.array(embed_texts(texts), dtype=float)
        ids = [f"auto:{uuid4().hex}" for _ in texts]
        self.vector_store.add(
            namespace=self.config.collections.autobiographical,
            ids=ids,
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    # ---- Profile facts ---------------------------------------------------
    def list_profile_facts(self, active_only: bool = True) -> List[ProfileFact]:
        return self.db.list_profile_facts(active_only=active_only)

    def set_profile_fact_active(self, fact_id: int, is_active: bool) -> None:
        self.db.set_profile_fact_active(fact_id, is_active)

    # ---- Tooling --------------------------------------------------------
    def log_tool_run(
        self,
        session_id: str,
        tool_name: str,
        input_payload: str,
        output_ref: Optional[str] = None,
    ) -> int:
        """Persist a tool invocation to SQLite."""

        return self.db.log_tool_run(session_id, tool_name, input_payload, output_ref)

    def recent_tool_runs(self, session_id: str, limit: int = 10):
        return self.db.recent_tool_runs(session_id, limit=limit)

    def cache_web_result(
        self,
        *,
        session_id: str,
        content: str,
        url: str,
        query_id: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
        session_mode: SessionMode = SessionMode.QUICK_LOOKUP,
    ) -> None:
        """Store a snippet fetched from the live web into the web cache collection."""

        meta = extra_meta.copy() if extra_meta else {}
        source_id = meta.get("source_id", url)
        if "fetched_at" not in meta:
            meta["fetched_at"] = int(time.time())
        doc = SourceDocument(
            id=str(source_id),
            source_type=meta.get("source_type", "live_web"),
            raw_text=content,
            cleaned_text=content,
            url=url,
            metadata={**meta, "session_id": session_id, "query_id": query_id},
        )
        self.ingestion_manager.ingest_document(doc, session_mode=session_mode)

    def process_tool_result(self, session_id: str, request: ToolRequest, result: ToolResult) -> None:
        """Persist bookkeeping for a tool result and cache outputs when applicable."""

        payload = json.dumps(
            {
                "query": request.query,
                "metadata": request.metadata,
            },
            ensure_ascii=False,
        )
        output_ref = result.metadata.get("url") or result.summary[:120]
        self.log_tool_run(session_id, result.tool_name, payload, output_ref)
        if (
            result.metadata.get("source_type") == "live_web"
            and result.content
            and not result.metadata.get("ingested")
        ):
            self.cache_web_result(
                session_id=session_id,
                content=result.content,
                url=result.metadata.get("url", result.summary),
                query_id=request.metadata.get("query_id"),
                extra_meta=result.metadata,
                session_mode=request.session_mode,
            )
