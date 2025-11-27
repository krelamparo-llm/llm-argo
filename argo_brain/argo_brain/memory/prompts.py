"""Prompt templates for the summarizer and memory writer."""

from __future__ import annotations

from typing import Iterable

from .db import MessageRecord

SESSION_SUMMARY_INSTRUCTIONS = """
You are Argo, a helpful assistant that maintains a concise summary of an ongoing
conversation. Compress the transcript into a short bullet list covering:
- user goals or projects
- preferences and constraints
- open questions or tasks still unresolved
Keep it under 200 words and update previous summaries instead of repeating
verbatim history. Respond with plain text.
""".strip()

MEMORY_WRITER_INSTRUCTIONS = """
You are Argo's autobiographical memory engine. Extract only long-lived,
reusable facts about the HUMAN USER (their preferences, projects, constraints,
or explicit goals) from the latest exchange and running summary. Ignore tool or
web outputs unless the user clearly confirms them as their own plans or beliefs.
Do NOT store general world knowledge, headlines, or temporary search results.
Return strict JSON in the shape:
{"memories": [{"text": "...", "type": "preference|project|fact|task"}, ...]}
Respond with {"memories": []} if nothing should be stored.
""".strip()


def format_messages_for_prompt(messages: Iterable[MessageRecord]) -> str:
    """Render stored messages into a readable transcript snippet."""

    lines = []
    for message in messages:
        prefix = "User" if message.role == "user" else "Assistant"
        lines.append(f"{prefix}: {message.content.strip()}")
    return "\n".join(lines)
