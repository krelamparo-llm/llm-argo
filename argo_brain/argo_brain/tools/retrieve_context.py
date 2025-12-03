"""RetrieveContextTool for just-in-time context retrieval (Phase 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .base import ToolExecutionError, ToolRequest, ToolResult

if TYPE_CHECKING:
    from ..memory.manager import MemoryManager


class RetrieveContextTool:
    """Retrieve full content for a specific memory chunk by ID.

    This tool implements the second part of Anthropic's 'just-in-time context
    retrieval' pattern. Instead of loading all context upfront, the model first
    sees lightweight identifiers (snippets) and then explicitly requests full
    content only for chunks it needs.

    This reduces token usage by 50-70% in typical research sessions.
    """

    name = "retrieve_context"
    description = """Retrieve full content for a specific memory chunk by its ID.

**When to use**:
- After memory_query shows relevant identifiers with snippets
- When you need the complete text to cite specific passages
- When the snippet alone is insufficient for your analysis
- ONLY retrieve chunks you actually need (saves tokens)

**Parameters**:
- chunk_id (str): The unique identifier of the chunk to retrieve
  Example: "rag:12345" or "auto:1701388800:0"
- namespace (str, optional): Memory namespace (default: RAG collection)

**Returns**: Full text content of the specified chunk

**Best practices**:
- First review snippets from memory_query to decide which chunks are worth retrieving
- Only retrieve chunks you will actually use in your response
- Prefer retrieving 1-2 highly relevant chunks over many marginally relevant ones
- Use the retrieved content to provide accurate citations

**Edge cases**:
- Returns error if chunk_id not found (may have expired or been deleted)
- Very large chunks may still be truncated for safety"""
    input_schema = {
        "type": "object",
        "properties": {
            "chunk_id": {
                "type": "string",
                "description": "The unique identifier of the chunk to retrieve",
            },
            "namespace": {
                "type": "string",
                "description": "Optional memory namespace (defaults to RAG collection)",
            },
        },
        "required": ["chunk_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Full text content"},
            "metadata": {"type": "object", "description": "Chunk metadata"},
        },
    }
    side_effects = "read_memory"

    def __init__(self, memory_manager: "MemoryManager") -> None:
        self.memory_manager = memory_manager

    def run(self, request: ToolRequest) -> ToolResult:
        chunk_id = request.metadata.get("chunk_id")
        if not chunk_id:
            raise ToolExecutionError("retrieve_context requires a 'chunk_id' parameter")

        namespace = request.metadata.get("namespace")

        content = self.memory_manager.retrieve_chunk_by_id(
            chunk_id,
            namespace=namespace,
        )

        if content is None:
            return ToolResult(
                tool_name=self.name,
                summary=f"Chunk '{chunk_id}' not found",
                content="",
                metadata={
                    "chunk_id": chunk_id,
                    "found": False,
                    "error": f"No chunk found with ID '{chunk_id}'",
                },
                snippets=[],
            )

        # Truncate very large content for safety
        MAX_CONTENT_LENGTH = 8000
        truncated = len(content) > MAX_CONTENT_LENGTH
        if truncated:
            content = content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated for token limits]"

        return ToolResult(
            tool_name=self.name,
            summary=f"Retrieved chunk '{chunk_id}' ({len(content)} chars)",
            content=content,
            metadata={
                "chunk_id": chunk_id,
                "found": True,
                "content_length": len(content),
                "truncated": truncated,
            },
            snippets=[content[:500]] if content else [],
        )


__all__ = ["RetrieveContextTool"]
