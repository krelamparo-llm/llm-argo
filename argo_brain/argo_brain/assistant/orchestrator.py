"""Assistant orchestration that glues memory, RAG, tools, and llama-server."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import CONFIG
from ..llm_client import ChatMessage, LLMClient
from ..core.memory.ingestion import IngestionManager
from ..core.memory.session import SessionMode
from ..memory.manager import MemoryContext, MemoryManager
from ..tools import MemoryQueryTool, MemoryWriteTool, WebAccessTool
from ..tools.base import Tool, ToolExecutionError, ToolRegistry, ToolRequest, ToolResult
from ..utils.json_helpers import extract_json_object

DEFAULT_SYSTEM_PROMPT = (
    "You are Argo, a personal AI running locally for Karl. Leverage the provided context, cite "
    "sources when possible, and be concise.\n"
    "You can call external tools when needed. To call a tool, respond ONLY with JSON in the form\n"
    '{"tool_name": "name", "arguments": {"key": "value"}}. After receiving tool results, continue\n'
    "reasoning and provide a final natural-language answer when the task is complete."
)


@dataclass
class AssistantResponse:
    """Container for the assistant output and context used."""

    text: str
    context: MemoryContext
    thought: Optional[str] = None
    raw_text: Optional[str] = None
    prompt_messages: Optional[List[ChatMessage]] = None
    tool_results: List[ToolResult] = field(default_factory=list)


class ArgoAssistant:
    """High-level assistant that routes through the memory manager."""

    MAX_TOOL_CALLS = 3

    def __init__(
        self,
        *,
        llm_client: Optional[LLMClient] = None,
        memory_manager: Optional[MemoryManager] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
        tool_registry: Optional[ToolRegistry] = None,
        default_session_mode: SessionMode = SessionMode.QUICK_LOOKUP,
        ingestion_manager: Optional[IngestionManager] = None,
    ) -> None:
        self.llm_client = llm_client or LLMClient()
        self.memory_manager = memory_manager or MemoryManager(llm_client=self.llm_client)
        self.ingestion_manager = ingestion_manager or getattr(self.memory_manager, "ingestion_manager")
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.config = CONFIG
        self.tool_registry = tool_registry or ToolRegistry()
        self.default_session_mode = default_session_mode
        if tools is None:
            tools = [
                WebAccessTool(ingestion_manager=self.ingestion_manager),
                MemoryQueryTool(memory_manager=self.memory_manager),
                MemoryWriteTool(ingestion_manager=self.ingestion_manager),
            ]
        if tools:
            for tool in tools:
                self.tool_registry.register(tool)

    def build_prompt(
        self,
        context: MemoryContext,
        user_message: str,
        session_mode: SessionMode,
    ) -> List[ChatMessage]:
        """Construct chat messages for llama-server."""

        messages: List[ChatMessage] = [ChatMessage(role="system", content=self.system_prompt)]
        manifest_text = self.tool_registry.manifest()
        if manifest_text and "No external tools" not in manifest_text:
            messages.append(ChatMessage(role="system", content=manifest_text))
        mode_description = {
            SessionMode.QUICK_LOOKUP: "You are in QUICK LOOKUP mode: answer concisely using available context.",
            SessionMode.RESEARCH: "You are in RESEARCH mode: explore multiple sources and synthesize findings.",
            SessionMode.INGEST: "You are in INGEST mode: help archive and summarize supplied material.",
        }[session_mode]
        messages.append(ChatMessage(role="system", content=mode_description))
        context_sections: List[str] = []
        if context.session_summary:
            context_sections.append(f"Session summary:\n{context.session_summary}")
        if context.autobiographical_chunks:
            formatted = "\n\n".join(
                f"- {chunk.text} (type: {chunk.metadata.get('type', 'fact')})"
                for chunk in context.autobiographical_chunks
            )
            context_sections.append(f"Autobiographical memory:\n{formatted}")
        if context.web_cache_chunks:
            formatted = "\n\n".join(
                f"[Web {idx+1}] (fetched {chunk.metadata.get('fetched_at', 'unknown')}) {chunk.text}"
                for idx, chunk in enumerate(context.web_cache_chunks)
            )
            context_sections.append(f"Recent web lookups:\n{formatted}")
        if context.rag_chunks:
            formatted = "\n\n".join(
                f"[RAG {idx+1}] {chunk.text}" for idx, chunk in enumerate(context.rag_chunks)
            )
            context_sections.append(f"Knowledge snippets:\n{formatted}")
        if context_sections:
            messages.append(
                ChatMessage(
                    role="system",
                    content="Additional context for Argo:\n" + "\n\n".join(context_sections),
                )
            )
        for message in context.short_term_messages:
            messages.append(ChatMessage(role=message.role, content=message.content))
        messages.append(ChatMessage(role="user", content=user_message))
        return messages

    def _split_think(self, response_text: str) -> tuple[Optional[str], str]:
        """Extract optional <think>...</think> content and return (think, final_text)."""

        match = re.search(r"<think>(.*?)</think>", response_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            cleaned = response_text.replace("<final>", "").replace("</final>", "").strip()
            return None, cleaned
        think_text = match.group(1).strip()
        final_text = (response_text[: match.start()] + response_text[match.end() :]).strip()
        final_text = final_text.replace("<final>", "").replace("</final>", "").strip()
        return think_text or None, final_text

    def _maybe_parse_tool_call(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Detect whether the LLM is requesting a tool call via JSON."""

        data = extract_json_object(response_text)
        if not isinstance(data, dict):
            return None
        tool_name = data.get("tool_name") or data.get("name")
        if not tool_name:
            return None
        arguments = data.get("arguments") or data.get("args") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        return {"tool_name": str(tool_name), "arguments": arguments}

    def _format_tool_result_for_prompt(self, result: ToolResult) -> str:
        metadata_preview = json.dumps(result.metadata, ensure_ascii=False)[:800]
        content_preview = (result.content or "")[:1200]
        return (
            f"Tool {result.tool_name} result summary: {result.summary}\n"
            f"Content:\n{content_preview}\n"
            f"Metadata: {metadata_preview}"
        )

    def send_message(
        self,
        session_id: str,
        user_message: str,
        *,
        tool_results: Optional[List[ToolResult]] = None,
        return_prompt: bool = False,
        session_mode: Optional[SessionMode] = None,
    ) -> AssistantResponse:
        """Process a new user message and return the assistant output."""

        active_mode = session_mode or self.default_session_mode
        self.memory_manager.ensure_session(session_id)
        tool_results_accum = list(tool_results or [])
        context = self.memory_manager.get_context_for_prompt(
            session_id,
            user_message,
            tool_results=tool_results_accum,
        )
        extra_messages: List[ChatMessage] = [
            ChatMessage(role="system", content=self._format_tool_result_for_prompt(result))
            for result in tool_results_accum
        ]
        iterations = 0
        response_text = ""
        while True:
            prompt_messages = self.build_prompt(context, user_message, active_mode) + extra_messages
            response_text = self.llm_client.chat(prompt_messages)
            tool_call = self._maybe_parse_tool_call(response_text)
            if tool_call and iterations < self.MAX_TOOL_CALLS:
                iterations += 1
                tool_name = tool_call["tool_name"]
                arguments = tool_call.get("arguments", {})
                if not isinstance(arguments, dict):
                    arguments = {}
                query_arg = (
                    str(arguments.get("query"))
                    if arguments.get("query") is not None
                    else arguments.get("url")
                )
                query_value = query_arg or user_message
                result = self.run_tool(
                    tool_name,
                    session_id,
                    str(query_value),
                    metadata=arguments,
                    session_mode=active_mode,
                )
                tool_results_accum.append(result)
                context = self.memory_manager.get_context_for_prompt(
                    session_id,
                    user_message,
                    tool_results=tool_results_accum,
                )
                call_json = json.dumps({"tool_name": tool_name, "arguments": arguments}, ensure_ascii=False)
                extra_messages.append(ChatMessage(role="assistant", content=f"TOOL_CALL {call_json}"))
                extra_messages.append(
                    ChatMessage(
                        role="system",
                        content=self._format_tool_result_for_prompt(result),
                    )
                )
                continue
            break

        thought, final_text = self._split_think(response_text)
        # Persist the cleaned final text so summaries/memories stay concise.
        self.memory_manager.record_interaction(session_id, user_message, final_text)
        return AssistantResponse(
            text=final_text,
            context=context,
            thought=thought,
            raw_text=response_text,
            prompt_messages=prompt_messages if return_prompt else None,
            tool_results=tool_results_accum,
        )

    def list_profile_facts(self) -> str:
        """Return a formatted string of stored profile facts."""

        facts = self.memory_manager.list_profile_facts()
        if not facts:
            return "No profile facts stored yet."
        formatted = [f"[{fact.id}] {fact.fact_text} (added {fact.created_at})" for fact in facts]
        return "\n".join(formatted)

    # ---- Tool helpers ---------------------------------------------------
    def available_tools(self) -> List[Tool]:
        return self.tool_registry.list_tools()

    def run_tool(
        self,
        tool_name: str,
        session_id: str,
        query: str,
        metadata: Optional[Dict[str, Any]] = None,
        session_mode: SessionMode = SessionMode.QUICK_LOOKUP,
    ) -> ToolResult:
        """Execute a registered tool and persist its output."""

        try:
            tool = self.tool_registry.get(tool_name)
        except KeyError as exc:
            raise ToolExecutionError(str(exc)) from exc
        request = ToolRequest(
            session_id=session_id,
            query=query,
            metadata=metadata or {},
            session_mode=session_mode,
        )
        result = tool.run(request)
        self.memory_manager.process_tool_result(session_id, request, result)
        return result
