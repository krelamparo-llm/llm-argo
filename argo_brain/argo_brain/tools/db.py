"""Read-only database query tool scaffolding."""

from __future__ import annotations

import logging
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..config import CONFIG
from .base import Tool, ToolExecutionError, ToolRequest, ToolResult


class QueryName(str, Enum):
    """Enumerates approved database queries."""

    MESSAGES_IN_RANGE = "messages_in_range"


_QUERY_TEMPLATES: Dict[QueryName, Dict[str, Any]] = {
    QueryName.MESSAGES_IN_RANGE: {
        "sql": (
            "SELECT session_id, role, content, created_at "
            "FROM messages "
            "WHERE created_at BETWEEN :start_ts AND :end_ts "
            "ORDER BY created_at DESC LIMIT :limit"
        ),
        "required": {"start_ts", "end_ts"},
        "optional": {"limit"},
        "defaults": {"limit": 50},
    },
}


class DatabaseQueryTool:
    """Executes pre-approved read-only SQL templates with parameters."""

    name = "db_query"
    description = (
        "Run a safe, read-only SQL query from a small allow-list. Provide query_name and params."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query_name": {"type": "string", "enum": [name.value for name in QueryName]},
            "params": {"type": "object"},
        },
        "required": ["query_name"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "rows": {"type": "array"},
            "query_name": {"type": "string"},
        },
    }
    side_effects = "read_db"

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path or CONFIG.paths.sqlite_path)
        self.logger = logging.getLogger("argo_brain.tools.db")

    def run(self, request: ToolRequest) -> ToolResult:
        query_name_raw = request.metadata.get("query_name") or request.query
        if not query_name_raw:
            raise ToolExecutionError("db_query requires 'query_name'")
        try:
            query_name = QueryName(query_name_raw)
        except ValueError as exc:  # noqa: PERF203 - explicit error message for policy
            raise ToolExecutionError(f"Unsupported query_name '{query_name_raw}'") from exc
        params = request.metadata.get("params") or {}
        if not isinstance(params, dict):
            raise ToolExecutionError("db_query params must be an object")
        rows = run_query(query_name, params=params, db_path=self.db_path)
        summary = f"Query {query_name.value} returned {len(rows)} rows"
        self.logger.info(
            "Database query executed",
            extra={"query_name": query_name.value, "rows": len(rows)},
        )
        return ToolResult(
            tool_name=self.name,
            summary=summary,
            content=str(rows[:2]),
            metadata={"query_name": query_name.value, "row_count": len(rows), "params": params},
            snippets=[str(row) for row in rows[:3]],
        )


def run_query(
    query_name: QueryName,
    *,
    params: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Execute a whitelisted query with defensive parameter handling."""

    template = _QUERY_TEMPLATES.get(query_name)
    if not template:
        raise ToolExecutionError(f"Query '{query_name.value}' is not configured")
    bound_params = _prepare_params(template, params or {})
    path = Path(db_path or CONFIG.paths.sqlite_path)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(template["sql"], bound_params)
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _prepare_params(template: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    required: Iterable[str] = template.get("required", set())
    optional: Iterable[str] = template.get("optional", set())
    defaults: Dict[str, Any] = template.get("defaults", {})
    normalized: Dict[str, Any] = {}
    for key in required:
        if key not in params and key not in defaults:
            raise ToolExecutionError(f"Missing required parameter '{key}'")
    for key, value in {**defaults, **params}.items():
        if key not in required and key not in optional:
            raise ToolExecutionError(f"Parameter '{key}' is not allowed for this query")
        if isinstance(value, str):
            normalized[key] = value
        elif isinstance(value, (int, float)):
            normalized[key] = int(value) if key == "limit" else value
        else:
            raise ToolExecutionError(f"Unsupported parameter type for '{key}'")
    if "limit" in normalized:
        normalized["limit"] = max(1, min(200, int(normalized["limit"])))
    return normalized


__all__ = ["DatabaseQueryTool", "QueryName", "run_query"]
