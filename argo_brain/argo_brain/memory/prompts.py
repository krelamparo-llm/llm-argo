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
reusable facts from the latest exchange and running summary. Good candidates are
preferences, ongoing projects, recurring constraints, or personal details that
will still matter later. Return strict JSON in the shape:
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
