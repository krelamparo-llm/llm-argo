"""Tool rendering for different model formats.

This module provides abstractions for rendering tools in various formats:
- TEXT_MANIFEST: Current text-based approach (improved, more concise)
- QWEN_XML: XML-style format for Qwen models
- CONCISE_TEXT: Minimal, token-efficient format
- OPENAI_TOOLS: OpenAI function calling format (future)
- ANTHROPIC_TOOLS: Anthropic tool format (future)
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Protocol

if TYPE_CHECKING:
    from .base import Tool


class ToolFormat(Enum):
    """Supported tool definition formats."""

    TEXT_MANIFEST = "text_manifest"  # Current approach (improved)
    QWEN_XML = "qwen_xml"  # Qwen-style XML descriptions
    CONCISE_TEXT = "concise_text"  # Minimal, token-efficient
    OPENAI_TOOLS = "openai_tools"  # OpenAI function calling (future)
    ANTHROPIC_TOOLS = "anthropic_tools"  # Anthropic tool_choice (future)


class ToolRenderer(Protocol):
    """Interface for rendering tools in different formats."""

    def render(self, tools: List[Tool], format: ToolFormat) -> Any:
        """Render tools in the specified format.

        Args:
            tools: List of tools to render
            format: Target format for rendering

        Returns:
            - For structured formats (OPENAI_TOOLS, ANTHROPIC_TOOLS): List[Dict]
            - For text formats (TEXT_MANIFEST, QWEN_XML, CONCISE_TEXT): str
        """
        ...


class DefaultToolRenderer:
    """Default implementation supporting multiple formats.

    This renderer provides format-independent tool rendering with support for:
    - Text manifests (current approach, improved for token efficiency)
    - XML manifests (for Qwen-style models)
    - Concise text (minimal token usage)
    - Structured formats (OpenAI, Anthropic - for future use)
    """

    def render(self, tools: List[Tool], format: ToolFormat) -> Any:
        """Render tools in the specified format.

        Args:
            tools: List of tools to render
            format: Target format for rendering

        Returns:
            Rendered tools in the specified format

        Raises:
            ValueError: If format is not supported
        """
        if format == ToolFormat.TEXT_MANIFEST:
            return self._to_text_manifest(tools)
        elif format == ToolFormat.QWEN_XML:
            return self._to_qwen_xml_manifest(tools)
        elif format == ToolFormat.CONCISE_TEXT:
            return self._to_concise_text(tools)
        elif format == ToolFormat.OPENAI_TOOLS:
            return self._to_openai_tools(tools)
        elif format == ToolFormat.ANTHROPIC_TOOLS:
            return self._to_anthropic_tools(tools)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _to_text_manifest(self, tools: List[Tool]) -> str:
        """Convert to improved text manifest (current approach, cleaner).

        This format is similar to the current implementation but more concise,
        extracting parameter documentation from JSON schema instead of dumping
        the raw schema.

        Token savings: ~20-30% vs current implementation
        """
        if not tools:
            return "No external tools available for this mode/phase."

        entries = []
        for tool in tools:
            desc = tool.description
            params = self._extract_param_docs(tool.input_schema)
            side_effects = getattr(tool, "side_effects", "none")
            when_to_use = getattr(tool, "when_to_use", None)

            entry_parts = [f"**{tool.name}**: {desc}"]

            if when_to_use:
                entry_parts.append(f"**When to use**: {when_to_use}")

            if params:
                entry_parts.append(f"**Parameters**: {params}")

            entry_parts.append(f"**Side effects**: {side_effects}")

            entries.append("\n".join(entry_parts))

        return "Available tools:\n\n" + "\n\n".join(entries)

    def _to_qwen_xml_manifest(self, tools: List[Tool]) -> str:
        """Generate XML-style manifest for Qwen models.

        This format uses XML-like tags to structure tool definitions,
        which some models (like Qwen) handle better than plain text.

        Example:
            <tools>
              <tool name='web_search'>
                <description>Search the web for current information</description>
                <parameters>query (string, required): Search query</parameters>
              </tool>
            </tools>
        """
        if not tools:
            return "<tools></tools>"

        entries = []
        for tool in tools:
            desc = tool.description
            params = self._extract_param_docs(tool.input_schema)
            when_to_use = getattr(tool, "when_to_use", None)

            parts = [f"  <tool name='{tool.name}'>"]
            parts.append(f"    <description>{desc}</description>")

            if when_to_use:
                parts.append(f"    <when_to_use>{when_to_use}</when_to_use>")

            if params:
                parts.append(f"    <parameters>{params}</parameters>")

            parts.append("  </tool>")
            entries.append("\n".join(parts))

        return "<tools>\n" + "\n".join(entries) + "\n</tools>"

    def _to_concise_text(self, tools: List[Tool]) -> str:
        """Generate minimal, token-efficient manifest.

        This format prioritizes token efficiency, stripping out all
        non-essential information. Best for modes with strict token budgets.

        Token savings: ~50-60% vs current implementation

        Example:
            Tools: web_search(query:str), web_access(url:str, format?:str)
        """
        if not tools:
            return "Tools: none"

        tool_sigs = []
        for tool in tools:
            params = self._extract_concise_params(tool.input_schema)
            tool_sigs.append(f"{tool.name}({params})")

        return "Tools: " + ", ".join(tool_sigs)

    def _to_openai_tools(self, tools: List[Tool]) -> List[Dict]:
        """Convert to OpenAI function calling format.

        This format is for future use when llama.cpp supports structured
        function calling. Tools are already defined with JSON Schema, so
        conversion is straightforward.

        Returns:
            List of tool definitions in OpenAI format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,  # Already JSON Schema!
                },
            }
            for tool in tools
        ]

    def _to_anthropic_tools(self, tools: List[Tool]) -> List[Dict]:
        """Convert to Anthropic tool format.

        Similar to OpenAI format but with slightly different structure.
        Also for future use.

        Returns:
            List of tool definitions in Anthropic format
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]

    def _extract_param_docs(self, schema: Dict) -> str:
        """Extract human-readable parameter docs from JSON schema.

        Args:
            schema: JSON Schema for tool parameters

        Returns:
            Human-readable parameter documentation

        Example:
            "query (string, required): Search query 2-100 chars,
             max_results (integer): Max results, default 5"
        """
        props = schema.get("properties", {})
        required = schema.get("required", [])

        if not props:
            return "none"

        docs = []
        for name, spec in props.items():
            req = ", required" if name in required else ""
            desc = spec.get("description", "")
            type_str = spec.get("type", "any")

            # Add type constraints if available
            constraints = []
            if "minLength" in spec or "maxLength" in spec:
                min_len = spec.get("minLength", "")
                max_len = spec.get("maxLength", "")
                if min_len and max_len:
                    constraints.append(f"{min_len}-{max_len} chars")
                elif min_len:
                    constraints.append(f"min {min_len} chars")
                elif max_len:
                    constraints.append(f"max {max_len} chars")

            if "default" in spec:
                constraints.append(f"default {spec['default']}")

            constraint_str = f" ({', '.join(constraints)})" if constraints else ""

            docs.append(f"{name} ({type_str}{req}): {desc}{constraint_str}")

        return ", ".join(docs)

    def _extract_concise_params(self, schema: Dict) -> str:
        """Extract minimal parameter signature from JSON schema.

        Args:
            schema: JSON Schema for tool parameters

        Returns:
            Concise parameter signature

        Example:
            "query:str, max_results?:int"
        """
        props = schema.get("properties", {})
        required = schema.get("required", [])

        if not props:
            return ""

        params = []
        for name, spec in props.items():
            type_str = spec.get("type", "any")
            # Shorten type names
            type_abbrev = {
                "string": "str",
                "integer": "int",
                "number": "num",
                "boolean": "bool",
                "array": "arr",
                "object": "obj",
            }.get(type_str, type_str)

            optional = "" if name in required else "?"
            params.append(f"{name}{optional}:{type_abbrev}")

        return ", ".join(params)


__all__ = [
    "ToolFormat",
    "ToolRenderer",
    "DefaultToolRenderer",
]
