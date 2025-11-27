"""SQLite persistence layer for Argo Brain's memory system."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from ..config import CONFIG


@dataclass
class MessageRecord:
    """Represents a stored chat message."""

    id: int
    session_id: str
    role: str
    content: str
    created_at: str


@dataclass
class ProfileFact:
    """Structured fact extracted about the user."""

    id: int
    fact_text: str
    user_id: str
    source_session_id: Optional[str]
    created_at: str
    is_active: bool


class MemoryDB:
    """Lightweight wrapper around a SQLite database."""

    def __init__(self, path: Path | str = CONFIG.paths.sqlite_path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session_created
                    ON messages(session_id, created_at);

                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY,
                    summary_text TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS profile_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    fact_text TEXT NOT NULL,
                    source_session_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS tool_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    input_payload TEXT NOT NULL,
                    output_ref TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_tool_runs_session_created
                    ON tool_runs(session_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS session_summary_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    snapshot_text TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                """
            )

    def ensure_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(id) VALUES (?)",
                (session_id,),
            )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self.ensure_session(session_id)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )

    def get_recent_messages(self, session_id: str, limit: int) -> List[MessageRecord]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = cursor.fetchall()
        records = [MessageRecord(**dict(row)) for row in rows]
        records.reverse()
        return records

    def get_all_messages(self, session_id: str, limit: Optional[int] = None) -> List[MessageRecord]:
        query = (
            "SELECT id, session_id, role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY created_at ASC"
        )
        params: tuple = (session_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (session_id, limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [MessageRecord(**dict(row)) for row in rows]

    def count_messages(self, session_id: str) -> int:
        with self._connect() as conn:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(count)

    def get_session_summary(self, session_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary_text FROM session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row[0] if row else None

    def upsert_session_summary(self, session_id: str, summary_text: str) -> None:
        self.ensure_session(session_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_summaries(session_id, summary_text)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary_text=excluded.summary_text,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (session_id, summary_text),
            )

    def add_profile_fact(
        self,
        fact_text: str,
        *,
        user_id: str = "default",
        source_session_id: Optional[str] = None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO profile_facts(fact_text, user_id, source_session_id)
                VALUES (?, ?, ?)
                """,
                (fact_text, user_id, source_session_id),
            )
            return int(cursor.lastrowid)

    def list_profile_facts(self, active_only: bool = True) -> List[ProfileFact]:
        query = (
            "SELECT id, fact_text, user_id, source_session_id, created_at, is_active "
            "FROM profile_facts"
        )
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [ProfileFact(**dict(row)) for row in rows]

    def set_profile_fact_active(self, fact_id: int, is_active: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE profile_facts SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, fact_id),
            )

    def log_tool_run(
        self,
        session_id: str,
        tool_name: str,
        input_payload: str,
        output_ref: Optional[str] = None,
    ) -> int:
        """Persist a tool invocation for traceability."""

        self.ensure_session(session_id)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tool_runs(session_id, tool_name, input_payload, output_ref)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, tool_name, input_payload, output_ref),
            )
            return int(cursor.lastrowid)

    def recent_tool_runs(self, session_id: str, limit: int = 10) -> List[ToolRunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, tool_name, input_payload, output_ref, created_at
                FROM tool_runs
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [ToolRunRecord(**dict(row)) for row in rows]

    def add_summary_snapshot(self, session_id: str, snapshot_text: str) -> int:
        """Persist a snapshot of the rolling session summary."""

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO session_summary_snapshots(session_id, snapshot_text)
                VALUES (?, ?)
                """,
                (session_id, snapshot_text),
            )
            return int(cursor.lastrowid)

    def list_summary_snapshots(self, session_id: str, limit: int = 5) -> List[SummarySnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, snapshot_text, created_at
                FROM session_summary_snapshots
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [SummarySnapshot(**dict(row)) for row in rows]
@dataclass
class ToolRunRecord:
    """Represents a logged tool execution."""

    id: int
    session_id: str
    tool_name: str
    input_payload: str
    output_ref: Optional[str]
    created_at: str

@dataclass
class SummarySnapshot:
    """Historical summary snapshot."""

    id: int
    session_id: str
    snapshot_text: str
    created_at: str
