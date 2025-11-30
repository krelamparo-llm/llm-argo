"""Tools that interface with Argo's memory stores."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from ..config import CONFIG
from ..core.memory.document import SourceDocument
from ..core.memory.ingestion import (
    IngestionManager,
    IngestionPolicy,
    get_default_ingestion_manager,
)
from ..embeddings import embed_single
from ..vector_store import get_vector_store
from .base import ToolExecutionError, Tool, ToolRequest, ToolResult


class MemoryQueryTool:
    """Query the user's personal knowledge base via vector search."""

    name = "memory_query"
    description = (
        "Search Karl's personal knowledge base (articles, transcripts, history) "
        "and return the most relevant snippets."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language query"},
            "top_k": {"type": "integer", "description": "Number of chunks to return", "default": 5},
            "namespace": {"type": "string", "description": "Optional memory namespace/collection"},
            "source_type": {"type": "string", "description": "Optional filter on stored metadata"},
            "filters": {"type": "object", "description": "Additional metadata filters"},
        },
        "required": ["query"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "snippets": {"type": "array", "items": {"type": "string"}},
            "metadata": {"type": "array", "items": {"type": "object"}},
        },
    }
    side_effects = "read_memory"

    def __init__(
        self,
        top_k: int = 5,
        *,
        vector_store=None,
        default_namespace: Optional[str] = None,
        embed_fn=None,
    ) -> None:
        self.top_k = top_k
        self.vector_store = vector_store or get_vector_store()
        self.default_namespace = default_namespace or CONFIG.collections.rag
        self.embed_fn = embed_fn or embed_single

    def run(self, request: ToolRequest) -> ToolResult:
        query = request.metadata.get("query") or request.query
        if not query:
            raise ToolExecutionError("memory_query requires a 'query' string")
        embedding = self.embed_fn(query)
        if not embedding:
            raise ToolExecutionError("Failed to embed the query text")
        namespace = request.metadata.get("namespace", self.default_namespace)
        top_k = int(request.metadata.get("top_k", self.top_k))
        filters = self._build_filters(request.metadata)
        documents = self.vector_store.query(
            namespace=namespace,
            query_embedding=np.array(embedding, dtype=float),
            k=top_k,
            filters=filters,
        )
        snippets = [doc.text[:500] for doc in documents]
        metadata = [doc.metadata for doc in documents]
        summary = f"Retrieved {len(snippets)} snippets for '{query}' from {namespace}."
        return ToolResult(
            tool_name=self.name,
            summary=summary,
            content="\n\n".join(snippets),
            metadata={
                "query": query,
                "top_k": top_k,
                "namespace": namespace,
                "filters": filters or {},
                "results": metadata,
            },
            snippets=snippets,
        )

    def _build_filters(self, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        source_type = metadata.get("source_type")
        if source_type:
            filters["source_type"] = source_type
        extra_filters = metadata.get("filters")
        if isinstance(extra_filters, dict):
            filters.update(extra_filters)
        return filters or None


class MemoryWriteTool:
    """Persist summarized knowledge into the personal knowledge base."""

    name = "memory_write"
    description = (
        "Store concise summaries or notes into Karl's personal knowledge base for future retrieval."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Content to store"},
            "source_type": {"type": "string", "description": "Logical source label", "default": "conversation_note"},
            "source_id": {"type": "string", "description": "Unique identifier for the source"},
            "url": {"type": "string", "description": "Optional URL associated with the note"},
            "policy": {
                "type": "string",
                "description": "Optional ingestion policy override (ephemeral|summary_only|full)",
            },
        },
        "required": ["text"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "stored": {"type": "boolean"},
            "source_id": {"type": "string"},
        },
    }
    side_effects = "writes_memory"

    def __init__(self, ingestion_manager: IngestionManager | None = None) -> None:
        self.ingestion_manager = ingestion_manager or get_default_ingestion_manager()

    def run(self, request: ToolRequest) -> ToolResult:
        text = request.metadata.get("text") or request.query
        if not text:
            raise ToolExecutionError("memory_write requires 'text' in metadata or query")
        source_type = request.metadata.get("source_type", "note")
        source_id = request.metadata.get("source_id") or f"memory:{request.session_id}:{abs(hash(text))}"
        url = request.metadata.get("url")
        policy_value = request.metadata.get("policy")
        policy = None
        if isinstance(policy_value, str):
            try:
                policy = IngestionPolicy(policy_value)
            except ValueError:
                policy = None
        doc = SourceDocument(
            id=source_id,
            source_type=source_type,
            raw_text=text,
            cleaned_text=text,
            url=url,
            metadata={"session_id": request.session_id},
        )
        intent = "explicit_save"
        self.ingestion_manager.ingest_document(
            doc,
            session_mode=request.session_mode,
            user_intent=intent,
            policy_override=policy,
        )
        summary = f"Stored note '{source_id}'"
        return ToolResult(
            tool_name=self.name,
            summary=summary,
            content=text,
            metadata={"source_id": source_id, "source_type": source_type, "url": url, "ingested": True},
            snippets=[text[:200]],
        )
