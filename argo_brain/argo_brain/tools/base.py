"""Base tool abstractions for Argo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from ..core.memory.session import SessionMode


@dataclass
class ToolRequest:
    """Structured information passed when invoking a tool."""

    session_id: str
    query: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_mode: SessionMode = SessionMode.QUICK_LOOKUP


@dataclass
class ToolResult:
    """Normalized result returned by any tool."""

    tool_name: str
    summary: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    snippets: List[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Render the tool result as a short block suitable for prompts."""

        lines = [f"Tool {self.tool_name}: {self.summary}".strip()]
        if self.snippets:
            lines.extend(f"- {snippet}" for snippet in self.snippets)
        return "\n".join(lines)


class Tool(Protocol):
    """Interface implemented by all tools."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    side_effects: str

    def run(self, request: ToolRequest) -> ToolResult:
        """Execute the tool and return a ToolResult."""


def format_tool_manifest_entry(tool: Tool) -> str:
    """Render a tool specification suitable for LLM instructions."""

    return (
        f"{tool.name}: {tool.description}\n"
        f"Input schema: {tool.input_schema}\n"
        f"Output schema: {tool.output_schema}\n"
        f"Side effects: {tool.side_effects}"
    )


class ToolExecutionError(RuntimeError):
    """Raised when a tool invocation fails."""


class ToolRegistry:
    """Simple in-memory registry of tool implementations."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        return self._tools[name]

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def manifest(self) -> str:
        """Render a manifest string summarizing all registered tools."""

        if not self._tools:
            return ""
        entries = [format_tool_manifest_entry(tool) for tool in self._tools.values()]
        return "Available tools:\n" + "\n\n".join(entries)


DEFAULT_TOOL_REGISTRY = ToolRegistry()
