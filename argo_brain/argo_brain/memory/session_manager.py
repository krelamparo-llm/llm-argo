"""Session lifecycle management for conversations."""

from __future__ import annotations

import logging
from typing import List, Optional

from ..config import CONFIG
from ..llm_client import ChatMessage, LLMClient
from .db import MemoryDB, MessageRecord
from .prompts import SESSION_SUMMARY_INSTRUCTIONS, format_messages_for_prompt


class SessionManager:
    """Manages conversation sessions, summaries, and message history."""

    def __init__(self, db: Optional[MemoryDB] = None, llm_client: Optional[LLMClient] = None):
        self.db = db or MemoryDB()
        self.llm_client = llm_client or LLMClient()
        self.config = CONFIG.memory
        self.logger = logging.getLogger("argo_brain.session")

    # ---- Session lifecycle -----------------------------------------------
    def ensure_session(self, session_id: str) -> None:
        """Create session if it doesn't exist."""
        self.db.ensure_session(session_id)

    def get_recent_messages(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[MessageRecord]:
        """Retrieve recent conversation turns."""
        limit = limit or self.config.short_term_window
        return self.db.get_recent_messages(session_id, limit)

    def record_turn(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """Persist a conversation turn and trigger summarization if needed."""
        self.db.add_message(session_id, "user", user_msg)
        self.db.add_message(session_id, "assistant", assistant_msg)
        self._maybe_update_summary(session_id)

    # ---- Summarization ---------------------------------------------------
    def get_session_summary(self, session_id: str) -> Optional[str]:
        """Retrieve rolling summary for session."""
        return self.db.get_session_summary(session_id)

    def _maybe_update_summary(self, session_id: str) -> Optional[str]:
        """Update rolling summary if interval reached."""
        summary_interval = self.config.summary_interval
        snapshot_interval = self.config.summary_snapshot_interval

        # Check if we should update the summary
        message_count = self.db.count_messages_since_summary(session_id)
        if message_count < summary_interval:
            return None

        # Fetch recent messages for summarization
        lookback = min(message_count, 200)  # Cap at 200 messages
        recent = self.db.get_recent_messages(session_id, lookback)

        if not recent:
            return None

        # Generate summary via LLM
        transcript = format_messages_for_prompt(recent)
        summary_prompt = [
            ChatMessage(role="system", content=SESSION_SUMMARY_INSTRUCTIONS),
            ChatMessage(role="user", content=transcript),
        ]

        try:
            new_summary = self.llm_client.chat(summary_prompt, temperature=0.3, max_tokens=400)
        except Exception as e:
            self.logger.error("Failed to generate session summary", exc_info=True, extra={"error": str(e)})
            return None

        cleaned = (new_summary or "").strip()
        if not cleaned:
            return None

        # Store the summary
        self.db.update_session_summary(session_id, cleaned)

        # Check if we should snapshot
        total_messages = len(self.db.get_all_messages(session_id))
        if total_messages >= snapshot_interval and total_messages % snapshot_interval == 0:
            self.db.add_summary_snapshot(session_id, cleaned)
            self.logger.info(
                "Created summary snapshot",
                extra={"session_id": session_id, "message_count": total_messages},
            )

        self.logger.info(
            "Updated session summary",
            extra={"session_id": session_id, "message_count": message_count},
        )

        return cleaned


__all__ = ["SessionManager"]
