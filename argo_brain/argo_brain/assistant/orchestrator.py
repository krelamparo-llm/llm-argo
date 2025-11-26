"""Assistant orchestration that glues memory, RAG, and llama-server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..config import CONFIG
from ..llm_client import ChatMessage, LLMClient
from ..memory.manager import MemoryContext, MemoryManager

DEFAULT_SYSTEM_PROMPT = (
    "You are Argo, a personal AI operating entirely on the user's local machine. "
    "Leverage the provided context, cite sources when possible, and be concise."
)


@dataclass
class AssistantResponse:
    """Container for the assistant output and context used."""

    text: str
    context: MemoryContext


class ArgoAssistant:
    """High-level assistant that routes through the memory manager."""

    def __init__(
        self,
        *,
        llm_client: Optional[LLMClient] = None,
        memory_manager: Optional[MemoryManager] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self.llm_client = llm_client or LLMClient()
        self.memory_manager = memory_manager or MemoryManager(llm_client=self.llm_client)
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.config = CONFIG

    def build_prompt(self, context: MemoryContext, user_message: str) -> List[ChatMessage]:
        """Construct chat messages for llama-server."""

        messages: List[ChatMessage] = [ChatMessage(role="system", content=self.system_prompt)]
        context_sections: List[str] = []
        if context.session_summary:
            context_sections.append(f"Session summary:\n{context.session_summary}")
        if context.autobiographical_chunks:
            formatted = "\n\n".join(
                f"- {chunk.text} (type: {chunk.metadata.get('type', 'fact')})"
                for chunk in context.autobiographical_chunks
            )
            context_sections.append(f"Autobiographical memory:\n{formatted}")
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

    def send_message(self, session_id: str, user_message: str) -> AssistantResponse:
        """Process a new user message and return the assistant output."""

        self.memory_manager.ensure_session(session_id)
        context = self.memory_manager.get_context_for_prompt(session_id, user_message)
        prompt_messages = self.build_prompt(context, user_message)
        response_text = self.llm_client.chat(prompt_messages)
        self.memory_manager.record_interaction(session_id, user_message, response_text)
        return AssistantResponse(text=response_text, context=context)

    def list_profile_facts(self) -> str:
        """Return a formatted string of stored profile facts."""

        facts = self.memory_manager.list_profile_facts()
        if not facts:
            return "No profile facts stored yet."
        formatted = [f"[{fact.id}] {fact.fact_text} (added {fact.created_at})" for fact in facts]
        return "\n".join(formatted)
