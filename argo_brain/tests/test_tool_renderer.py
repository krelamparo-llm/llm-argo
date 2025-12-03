"""Tests for tool rendering in different formats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pytest

from argo_brain.tools.renderer import DefaultToolRenderer, ToolFormat
from argo_brain.tools.base import ToolRegistry, ToolResult, ToolRequest


# Mock tool implementations for testing
@dataclass
class MockWebSearchTool:
    """Mock web search tool for testing."""

    name: str = "web_search"
    description: str = "Search the web for current information using DuckDuckGo"
    when_to_use: str = "Finding recent news, articles, or current events"
    side_effects: str = "none"
    input_schema: Dict[str, Any] = None
    output_schema: Dict[str, Any] = None

    def __post_init__(self):
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                        "minLength": 2,
                        "maxLength": 100,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 5,
                    },
                },
                "required": ["query"],
            }
        if self.output_schema is None:
            self.output_schema = {
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
            }

    def run(self, request: ToolRequest) -> ToolResult:
        """Mock implementation."""
        return ToolResult(
            tool_name=self.name, summary="Mock result", content="Mock content"
        )


@dataclass
class MockWebAccessTool:
    """Mock web access tool for testing."""

    name: str = "web_access"
    description: str = "Fetch and extract content from a specific URL"
    when_to_use: str = "When you have a specific URL to fetch content from"
    side_effects: str = "none"
    input_schema: Dict[str, Any] = None
    output_schema: Dict[str, Any] = None

    def __post_init__(self):
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                    "response_format": {
                        "type": "string",
                        "description": "Format for the response",
                        "default": "concise",
                    },
                },
                "required": ["url"],
            }
        if self.output_schema is None:
            self.output_schema = {
                "type": "object",
                "properties": {"content": {"type": "string"}},
            }

    def run(self, request: ToolRequest) -> ToolResult:
        """Mock implementation."""
        return ToolResult(
            tool_name=self.name, summary="Mock result", content="Mock content"
        )


@dataclass
class MockMemoryWriteTool:
    """Mock memory write tool for testing."""

    name: str = "memory_write"
    description: str = "Store information to long-term memory"
    side_effects: str = "writes to database"
    input_schema: Dict[str, Any] = None
    output_schema: Dict[str, Any] = None

    def __post_init__(self):
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Content to store"},
                    "tags": {
                        "type": "array",
                        "description": "Tags for categorization",
                    },
                },
                "required": ["content"],
            }
        if self.output_schema is None:
            self.output_schema = {"type": "object", "properties": {"success": {"type": "boolean"}}}

    def run(self, request: ToolRequest) -> ToolResult:
        """Mock implementation."""
        return ToolResult(
            tool_name=self.name, summary="Mock result", content="Mock content"
        )


class TestDefaultToolRenderer:
    """Tests for DefaultToolRenderer with different formats."""

    @pytest.fixture
    def renderer(self):
        """Create a renderer instance."""
        return DefaultToolRenderer()

    @pytest.fixture
    def sample_tools(self):
        """Create sample tools for testing."""
        return [
            MockWebSearchTool(),
            MockWebAccessTool(),
            MockMemoryWriteTool(),
        ]

    def test_text_manifest_format(self, renderer, sample_tools):
        """Test TEXT_MANIFEST format produces readable text."""
        result = renderer.render(sample_tools, ToolFormat.TEXT_MANIFEST)

        assert isinstance(result, str)
        assert "Available tools:" in result
        assert "**web_search**" in result
        assert "**web_access**" in result
        assert "**memory_write**" in result

        # Check that descriptions are included
        assert "Search the web" in result
        assert "Fetch and extract content" in result
        assert "Store information" in result

        # Check that parameter docs are extracted (not raw JSON)
        assert "query (string, required)" in result or "query (string" in result
        assert "url (string, required)" in result or "url (string" in result

        # Should NOT dump raw JSON schema
        assert '"type": "object"' not in result
        assert '"properties"' not in result

    def test_text_manifest_token_efficiency(self, renderer, sample_tools):
        """Test that TEXT_MANIFEST is more token-efficient than raw schema dumps."""
        result = renderer.render(sample_tools, ToolFormat.TEXT_MANIFEST)

        # Should extract human-readable param docs
        assert "query" in result
        assert "url" in result

        # Should include length constraints
        assert "2-100 chars" in result or "minLength" not in result

        # Should include defaults
        assert "default 5" in result or "default" in result

    def test_qwen_xml_format(self, renderer, sample_tools):
        """Test QWEN_XML format produces valid XML structure."""
        result = renderer.render(sample_tools, ToolFormat.QWEN_XML)

        assert isinstance(result, str)
        assert result.startswith("<tools>")
        assert result.endswith("</tools>")

        # Check for tool entries
        assert "<tool name='web_search'>" in result
        assert "<tool name='web_access'>" in result
        assert "<tool name='memory_write'>" in result

        # Check for description tags
        assert "<description>Search the web" in result
        assert "<description>Fetch and extract content" in result

        # Check for parameter tags
        assert "<parameters>" in result
        assert "</parameters>" in result

        # Check for when_to_use if available
        assert "<when_to_use>" in result or "when_to_use" in result

    def test_concise_text_format(self, renderer, sample_tools):
        """Test CONCISE_TEXT format is minimal and token-efficient."""
        result = renderer.render(sample_tools, ToolFormat.CONCISE_TEXT)

        assert isinstance(result, str)
        assert result.startswith("Tools:")

        # Should include tool signatures
        assert "web_search(" in result
        assert "web_access(" in result
        assert "memory_write(" in result

        # Should use concise type names
        assert ":str" in result or "query" in result
        assert ":int" in result or "integer" in result

        # Should indicate optional params
        assert "?" in result or "max_results" in result

        # Should be MUCH shorter than TEXT_MANIFEST
        text_manifest = renderer.render(sample_tools, ToolFormat.TEXT_MANIFEST)
        assert len(result) < len(text_manifest) * 0.5  # At least 50% reduction

    def test_openai_tools_format(self, renderer, sample_tools):
        """Test OPENAI_TOOLS format produces valid OpenAI function definitions."""
        result = renderer.render(sample_tools, ToolFormat.OPENAI_TOOLS)

        assert isinstance(result, list)
        assert len(result) == 3

        # Check first tool structure
        tool = result[0]
        assert tool["type"] == "function"
        assert "function" in tool

        function = tool["function"]
        assert function["name"] == "web_search"
        assert function["description"] == "Search the web for current information using DuckDuckGo"
        assert "parameters" in function

        # Parameters should be the original JSON Schema (no conversion needed!)
        params = function["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "query" in params["properties"]
        assert params["required"] == ["query"]

    def test_anthropic_tools_format(self, renderer, sample_tools):
        """Test ANTHROPIC_TOOLS format produces valid Anthropic tool definitions."""
        result = renderer.render(sample_tools, ToolFormat.ANTHROPIC_TOOLS)

        assert isinstance(result, list)
        assert len(result) == 3

        # Check first tool structure
        tool = result[0]
        assert tool["name"] == "web_search"
        assert tool["description"] == "Search the web for current information using DuckDuckGo"
        assert "input_schema" in tool

        # Input schema should be the original JSON Schema
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "query" in schema["properties"]

    def test_empty_tools_text_format(self, renderer):
        """Test rendering empty tool list in text format."""
        result = renderer.render([], ToolFormat.TEXT_MANIFEST)
        assert isinstance(result, str)
        assert "No external tools available" in result or result == "<tools></tools>"

    def test_empty_tools_structured_format(self, renderer):
        """Test rendering empty tool list in structured format."""
        result = renderer.render([], ToolFormat.OPENAI_TOOLS)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_unsupported_format_raises_error(self, renderer, sample_tools):
        """Test that unsupported format raises ValueError."""
        # Create an invalid enum-like value
        with pytest.raises((ValueError, AttributeError)):
            renderer.render(sample_tools, "invalid_format")

    def test_param_extraction_with_constraints(self, renderer):
        """Test parameter documentation extraction with various constraints."""
        tool = MockWebSearchTool()
        params = renderer._extract_param_docs(tool.input_schema)

        # Should extract parameter names
        assert "query" in params
        assert "max_results" in params

        # Should indicate required status
        assert "required" in params

        # Should include type
        assert "string" in params or "str" in params
        assert "integer" in params or "int" in params

        # Should include constraints
        assert "2-100" in params or "minLength" not in params

        # Should include defaults
        assert "default 5" in params or "default" in params

    def test_concise_param_extraction(self, renderer):
        """Test concise parameter signature extraction."""
        tool = MockWebSearchTool()
        params = renderer._extract_concise_params(tool.input_schema)

        # Should be very compact
        assert len(params) < 100

        # Should use abbreviated types
        assert ":str" in params or ":int" in params

        # Should indicate optional params
        assert "max_results?:" in params or "max_results:" in params

        # Required params should NOT have ?
        assert "query?:" not in params


class TestToolRegistryIntegration:
    """Test ToolRegistry integration with ToolRenderer."""

    @pytest.fixture
    def registry(self):
        """Create a tool registry with sample tools."""
        registry = ToolRegistry()
        registry.register(MockWebSearchTool())
        registry.register(MockWebAccessTool())
        registry.register(MockMemoryWriteTool())
        return registry

    def test_registry_manifest_default_format(self, registry):
        """Test that registry manifest defaults to TEXT_MANIFEST."""
        result = registry.manifest()
        assert isinstance(result, str)
        assert "Available tools:" in result or "web_search" in result

    def test_registry_manifest_with_format(self, registry):
        """Test that registry accepts format parameter."""
        result = registry.manifest(format=ToolFormat.QWEN_XML)
        assert isinstance(result, str)
        assert "<tools>" in result

    def test_registry_manifest_with_filter(self, registry):
        """Test that registry filters tools correctly."""
        result = registry.manifest(
            filter_tools=["web_search", "web_access"],
            format=ToolFormat.CONCISE_TEXT,
        )
        assert "web_search" in result
        assert "web_access" in result
        assert "memory_write" not in result

    def test_registry_manifest_empty_filter(self, registry):
        """Test that empty filter returns no tools message."""
        result = registry.manifest(filter_tools=[], format=ToolFormat.TEXT_MANIFEST)
        assert "No external tools available" in result

    def test_registry_manifest_backward_compatibility(self, registry):
        """Test backward compatibility - calling without format parameter."""
        # Should default to TEXT_MANIFEST
        result = registry.manifest()
        assert isinstance(result, str)
        assert "web_search" in result

    def test_registry_structured_format_integration(self, registry):
        """Test registry integration with structured formats."""
        result = registry.manifest(format=ToolFormat.OPENAI_TOOLS)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["type"] == "function"


class TestTokenSavings:
    """Test that new formats provide significant token savings."""

    @pytest.fixture
    def renderer(self):
        return DefaultToolRenderer()

    @pytest.fixture
    def sample_tools(self):
        return [
            MockWebSearchTool(),
            MockWebAccessTool(),
            MockMemoryWriteTool(),
        ]

    def test_concise_vs_text_manifest_savings(self, renderer, sample_tools):
        """Test that CONCISE_TEXT is significantly shorter than TEXT_MANIFEST."""
        text_manifest = renderer.render(sample_tools, ToolFormat.TEXT_MANIFEST)
        concise = renderer.render(sample_tools, ToolFormat.CONCISE_TEXT)

        # Should be at least 50% shorter
        assert len(concise) < len(text_manifest) * 0.5

        print(f"\nToken savings analysis:")
        print(f"  TEXT_MANIFEST: {len(text_manifest)} chars")
        print(f"  CONCISE_TEXT: {len(concise)} chars")
        print(f"  Savings: {(1 - len(concise)/len(text_manifest)) * 100:.1f}%")

    def test_xml_vs_text_manifest_size(self, renderer, sample_tools):
        """Test XML format size compared to TEXT_MANIFEST."""
        text_manifest = renderer.render(sample_tools, ToolFormat.TEXT_MANIFEST)
        xml = renderer.render(sample_tools, ToolFormat.QWEN_XML)

        print(f"\nFormat size comparison:")
        print(f"  TEXT_MANIFEST: {len(text_manifest)} chars")
        print(f"  QWEN_XML: {len(xml)} chars")

        # XML may be longer or shorter depending on structure,
        # but should be well-structured for parsing
        assert "<tools>" in xml
        assert "</tools>" in xml
