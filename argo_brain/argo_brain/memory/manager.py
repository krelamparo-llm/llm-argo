"""High-level memory orchestration for Argo Brain."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import uuid4

from chromadb import PersistentClient
from chromadb.api.models.Collection import Collection

from ..config import CONFIG
from ..embeddings import embed_single, embed_texts
from ..llm_client import ChatMessage, LLMClient
from ..rag import RetrievedChunk, ingest_web_result, retrieve_knowledge
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
        self._chroma_client = PersistentClient(path=str(self.config.paths.vector_db_path))
        self._autobio_collection = self._chroma_client.get_or_create_collection(
            name=self.config.collections.autobiographical,
            metadata={"description": "Argo autobiographical memory"},
        )

    # ---- Session helpers -------------------------------------------------
    def ensure_session(self, session_id: str) -> None:
        self.db.ensure_session(session_id)

    # ---- Retrieval -------------------------------------------------------
    def get_context_for_prompt(self, session_id: str, user_message: str) -> MemoryContext:
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
        web_cache_chunks = retrieve_knowledge(
            user_message,
            top_k=max(3, mem_cfg.rag_k // 2),
            collection_name=self.config.collections.web_cache,
        )
        self.logger.info(
            "Prepared context",
            extra={
                "session_id": session_id,
                "short_term": len(short_term),
                "auto_chunks": len(auto_chunks),
                "rag_chunks": len(rag_chunks),
                "web_cache_chunks": len(web_cache_chunks),
                "has_summary": bool(summary),
            },
        )
        return MemoryContext(
            short_term_messages=short_term,
            session_summary=summary,
            autobiographical_chunks=auto_chunks,
            rag_chunks=rag_chunks,
            web_cache_chunks=web_cache_chunks,
        )

    def _retrieve_autobiographical(self, query: str, top_k: int) -> List[AutobiographicalChunk]:
        if not query.strip():
            return []
        embedding = embed_single(query)
        if not embedding:
            return []
        response = self._autobio_collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
        )
        docs = response.get("documents", [[]])[0]
        metas = response.get("metadatas", [[]])[0]
        ids = response.get("ids", [[]])[0]
        distances = response.get("distances", [[]])[0]
        chunks: List[AutobiographicalChunk] = []
        for doc, meta, chunk_id, dist in zip(docs, metas, ids, distances):
            chunks.append(
                AutobiographicalChunk(
                    text=doc,
                    metadata=meta or {},
                    chunk_id=chunk_id,
                    distance=dist,
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
        embeddings = embed_texts(texts)
        ids = [f"auto:{uuid4().hex}" for _ in texts]
        self._autobio_collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
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
    ) -> None:
        """Store a snippet fetched from the live web into the web cache collection."""

        meta = extra_meta or {}
        source_id = meta.get("source_id", url)
        ingest_web_result(
            content,
            source_id=source_id,
            url=url,
            query_id=query_id,
            extra_meta={**meta, "session_id": session_id},
        )
