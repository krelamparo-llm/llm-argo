"""Tools that interface with Argo's memory stores."""

from __future__ import annotations

from ..config import CONFIG
from ..core.memory.document import SourceDocument
from ..core.memory.ingestion import (
    IngestionManager,
    IngestionPolicy,
    get_default_ingestion_manager,
)
from ..rag import retrieve_knowledge
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

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def run(self, request: ToolRequest) -> ToolResult:
        query = request.metadata.get("query") or request.query
        if not query:
            raise ToolExecutionError("memory_query requires a 'query' string")
        top_k = int(request.metadata.get("top_k", self.top_k))
        chunks = retrieve_knowledge(query, top_k=top_k)
        snippets = [chunk.text[:500] for chunk in chunks]
        metadata = [chunk.metadata for chunk in chunks]
        summary = f"Retrieved {len(snippets)} snippets for '{query}'."
        return ToolResult(
            tool_name=self.name,
            summary=summary,
            content="\n\n".join(snippets),
            metadata={"query": query, "top_k": top_k, "results": metadata},
            snippets=snippets,
        )


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
