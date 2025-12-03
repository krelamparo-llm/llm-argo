# ToolRenderer Implementation Analysis

**Date**: December 2, 2025
**Complexity**: 🟡 **MEDIUM** (not as high as initially estimated)
**Effort**: ~2-3 days for full implementation
**Value**: 🔴 **HIGH** - Cleaner architecture, future-proof for structured function calling

---

## Executive Summary

**Actual Effort**: LESS than initially estimated. We already have:
- ✅ Tools with proper JSON Schema (`input_schema`, `output_schema`)
- ✅ Tool registry that knows about all tools
- ✅ Dual parsing support (XML + JSON)

**What's Missing**: Just a rendering abstraction layer between `ToolRegistry` and prompt assembly.

---

## Current State Analysis

### What We Have ✅

**1. Tools Already Have JSON Schema** ([search.py:41-55](argo_brain/argo_brain/tools/search.py#L41-L55))
```python
class WebSearchTool:
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }
```

This is **already OpenAI-compatible JSON Schema**! No conversion needed.

**2. Text Manifest Generation** ([base.py:52-60](argo_brain/argo_brain/tools/base.py#L52-L60))
```python
def format_tool_manifest_entry(tool: Tool) -> str:
    return (
        f"{tool.name}: {tool.description}\n"
        f"Input schema: {tool.input_schema}\n"
        ...
    )
```

This works but dumps raw JSON into text, which is:
- ❌ Redundant (description is in the schema AND as text)
- ❌ Hard to parse for models
- ❌ Verbose (wastes tokens)

**3. ToolRegistry** ([base.py:85-91](argo_brain/argo_brain/tools/base.py#L85-L91))
```python
def manifest(self, filter_tools: Optional[List[str]] = None) -> str:
    tools = [self._tools[name] for name in filter_tools ...]
    entries = [format_tool_manifest_entry(tool) for tool in tools]
    return "Available tools:\n" + "\n\n".join(entries)
```

Returns text string currently, but could easily return structured data.

---

## What ToolRenderer Would Look Like

### Core Interface (Simple!)

```python
from typing import List, Dict, Any, Protocol
from enum import Enum

class ToolFormat(Enum):
    """Supported tool definition formats."""
    OPENAI_TOOLS = "openai_tools"        # OpenAI function calling
    ANTHROPIC_TOOLS = "anthropic_tools"  # Anthropic tool_choice
    TEXT_MANIFEST = "text_manifest"      # Current approach (fallback)
    QWEN_XML = "qwen_xml"                # Qwen-style XML descriptions


class ToolRenderer(Protocol):
    """Interface for rendering tools in different formats."""

    def render(self, tools: List[Tool], format: ToolFormat) -> Any:
        """Render tools in the specified format.

        Returns:
            - For OPENAI_TOOLS: List[Dict] (to send in API payload)
            - For TEXT_MANIFEST: str (to inject in prompt)
        """
        ...


class DefaultToolRenderer:
    """Default implementation supporting multiple formats."""

    def render(self, tools: List[Tool], format: ToolFormat) -> Any:
        """Render tools in the specified format."""
        if format == ToolFormat.OPENAI_TOOLS:
            return self._to_openai_tools(tools)
        elif format == ToolFormat.ANTHROPIC_TOOLS:
            return self._to_anthropic_tools(tools)
        elif format == ToolFormat.TEXT_MANIFEST:
            return self._to_text_manifest(tools)
        elif format == ToolFormat.QWEN_XML:
            return self._to_qwen_xml_manifest(tools)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _to_openai_tools(self, tools: List[Tool]) -> List[Dict]:
        """Convert to OpenAI function calling format."""
        return [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema  # ← Already JSON Schema!
            }
        } for tool in tools]

    def _to_anthropic_tools(self, tools: List[Tool]) -> List[Dict]:
        """Convert to Anthropic tool format."""
        return [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema
        } for tool in tools]

    def _to_text_manifest(self, tools: List[Tool]) -> str:
        """Current text-based approach (fallback)."""
        entries = []
        for tool in tools:
            # Cleaner than current: extract description from schema if available
            desc = tool.description
            params = self._extract_param_docs(tool.input_schema)

            entry = f"**{tool.name}**: {desc}\n"
            if params:
                entry += f"Parameters: {params}"
            entries.append(entry)

        return "Available tools:\n\n" + "\n\n".join(entries)

    def _to_qwen_xml_manifest(self, tools: List[Tool]) -> str:
        """Generate XML-style manifest for Qwen models."""
        entries = []
        for tool in tools:
            params = self._extract_param_docs(tool.input_schema)
            entries.append(
                f"<tool name='{tool.name}'>\n"
                f"  <description>{tool.description}</description>\n"
                f"  <parameters>{params}</parameters>\n"
                f"</tool>"
            )
        return "<tools>\n" + "\n".join(entries) + "\n</tools>"

    def _extract_param_docs(self, schema: Dict) -> str:
        """Extract human-readable parameter docs from JSON schema."""
        props = schema.get("properties", {})
        required = schema.get("required", [])

        docs = []
        for name, spec in props.items():
            req = " (required)" if name in required else ""
            desc = spec.get("description", "")
            type_str = spec.get("type", "any")
            docs.append(f"{name} ({type_str}){req}: {desc}")

        return ", ".join(docs)
```

---

## Integration Points

### 1. ToolRegistry (Minimal Change)

```python
class ToolRegistry:
    def __init__(self, renderer: Optional[ToolRenderer] = None):
        self._tools = {}
        self.renderer = renderer or DefaultToolRenderer()

    def manifest(
        self,
        filter_tools: Optional[List[str]] = None,
        format: ToolFormat = ToolFormat.TEXT_MANIFEST
    ) -> Any:
        """Render tools in specified format."""
        tools = self._get_filtered_tools(filter_tools)
        return self.renderer.render(tools, format)

    def _get_filtered_tools(self, filter_tools: Optional[List[str]]) -> List[Tool]:
        """Get filtered list of tools."""
        if filter_tools is not None:
            return [self._tools[name] for name in filter_tools if name in self._tools]
        return list(self._tools.values())
```

**Change Impact**: ~10 lines modified in `base.py`

### 2. Orchestrator (Small Changes)

**Current** ([orchestrator.py:479](argo_brain/argo_brain/assistant/orchestrator.py#L479)):
```python
manifest_text = self.tool_registry.manifest(filter_tools=available_tools)
if manifest_text and "No external tools" not in manifest_text:
    messages.append(ChatMessage(role="system", content=manifest_text))
```

**With ToolRenderer** (when backend supports structured tools):
```python
# Determine format based on backend capabilities
if self.llm_client.supports_function_calling:
    # Use structured function calling (preferred)
    tool_defs = self.tool_registry.manifest(
        filter_tools=available_tools,
        format=ToolFormat.OPENAI_TOOLS
    )
    # Pass to LLM client as structured tools
    response = self.llm_client.chat(
        messages,
        tools=tool_defs,  # ← New parameter
        ...
    )
else:
    # Fallback to text manifest
    manifest_text = self.tool_registry.manifest(
        filter_tools=available_tools,
        format=ToolFormat.TEXT_MANIFEST
    )
    messages.append(ChatMessage(role="system", content=manifest_text))
```

**Change Impact**: ~15 lines in `orchestrator.py`, conditional on backend support

### 3. ModelPromptConfig Integration (Future)

```yaml
# argo_prompts.yaml
tool_calling:
  format: "openai_tools"  # or "text_manifest", "anthropic_tools"
  manifest_style: "concise"  # or "verbose"
```

```python
# In orchestrator
tool_format = ToolFormat(self.prompt_config.tool_calling.format)
manifest = self.tool_registry.manifest(filter_tools=..., format=tool_format)
```

**Change Impact**: ~5 lines in orchestrator, extend YAML schema

---

## Effort Breakdown

| Task | Effort | Files Changed |
|------|--------|---------------|
| Create `ToolRenderer` classes | 2 hours | New file: `tools/renderer.py` |
| Update `ToolRegistry.manifest()` | 1 hour | Modify: `tools/base.py` |
| Add `ToolFormat` enum | 30 min | New or in `tools/renderer.py` |
| Update orchestrator (text path) | 1 hour | Modify: `assistant/orchestrator.py` |
| Add tests | 2 hours | New: `tests/test_tool_renderer.py` |
| **Total (Phase 1: Text)** | **~6-7 hours** | **3 files** |
| | | |
| Add `LLMClient.supports_function_calling` | 30 min | Modify: `llm_client.py` |
| Update LLMClient to accept `tools` param | 2 hours | Modify: `llm_client.py` |
| Update orchestrator (structured path) | 2 hours | Modify: `assistant/orchestrator.py` |
| Integration testing | 2 hours | Extend: `tests/test_tool_renderer.py` |
| **Total (Phase 2: Structured)** | **~13 hours (2 days)** | **5 files** |

---

## Why This Is Actually Easier Than Expected

### 1. We Already Have JSON Schema ✅
No need to convert from some other format. Tools are already spec'd correctly.

### 2. It's Additive, Not Replacement
- Phase 1: Add `ToolRenderer`, keep text manifest as default
- Phase 2: Add structured calling when llama-server supports it
- No breaking changes at any point

### 3. Small Surface Area
Only 3 main touch points:
- `ToolRegistry.manifest()` - add `format` parameter
- `Orchestrator.build_prompt()` - conditional based on format
- `LLMClient.chat()` - (later) accept `tools` parameter

### 4. Current Code Is Well-Structured
The `Tool` protocol already has all the metadata we need:
- `name` ✅
- `description` ✅
- `input_schema` ✅ (JSON Schema)
- `output_schema` ✅

---

## Refactor Depth: **SHALLOW**

**Core Changes**:
- ✅ Tool definitions: **NO CHANGES** (already have schemas)
- ✅ Tool implementations: **NO CHANGES** (they just implement `run()`)
- 🔧 `ToolRegistry`: Small change (add `format` param, delegate to renderer)
- 🔧 `Orchestrator`: Small change (conditional on format)
- 📦 New: `ToolRenderer` class (new file, no breaking changes)

**Backward Compatibility**: 100%
- Default format: `TEXT_MANIFEST` (current behavior)
- Existing code works unchanged
- Opt-in to structured calling via config

---

## Benefits of Implementing Now (vs Later)

### Implement Now ✅

**Pros**:
1. **Cleaner architecture today** - Separation of concerns
2. **Easier testing** - Can test different formats independently
3. **Token savings** - Better text manifests (more concise)
4. **Ready for llama.cpp function calling** - When it ships, we're ready
5. **Multi-backend support** - Easy to add OpenAI/Anthropic backends later

**Cons**:
1. ~2 days of work
2. Slight complexity increase (but well-abstracted)

### Implement Later ❌

**Pros**:
1. Less work now

**Cons**:
1. **Harder to retrofit** - More code to change later
2. **Miss token savings** - Current text manifests are verbose
3. **Technical debt** - Keeps growing

---

## Recommended Approach

### Phase 1: ToolRenderer with Text Formats (Now - 1 day)

**Goal**: Clean up text manifests, add abstraction

```python
# Implement these formats:
- TEXT_MANIFEST (current, improved)
- QWEN_XML (for Qwen models)
- CONCISE_TEXT (minimal, token-efficient)

# Benefits:
- Immediate token savings (10-20% on tool manifests)
- Cleaner code
- Easy to test
```

**Deliverables**:
- [ ] `tools/renderer.py` - ToolRenderer classes
- [ ] Update `ToolRegistry.manifest()` - add format parameter
- [ ] Update `Orchestrator` - use renderer for text
- [ ] Tests for multiple text formats

### Phase 2: Structured Function Calling (When llama-server supports it)

**Goal**: Use native function calling when available

```python
# Implement these formats:
- OPENAI_TOOLS (for OpenAI-compatible backends)
- ANTHROPIC_TOOLS (for Anthropic-compatible backends)

# Benefits:
- More reliable tool parsing
- Model-native function calling
- Better error messages
```

**Deliverables**:
- [ ] Extend `ToolRenderer` with structured formats
- [ ] Update `LLMClient` - accept `tools` parameter
- [ ] Update `Orchestrator` - conditional based on backend
- [ ] Tests for structured calling

---

## Minimal Viable Implementation (4 hours)

If we want **just the abstraction without new formats**:

```python
# 1. Create tools/renderer.py (1 hour)
class ToolRenderer:
    def render_text(self, tools: List[Tool]) -> str:
        # Move current logic from format_tool_manifest_entry
        pass

# 2. Update ToolRegistry (30 min)
class ToolRegistry:
    def manifest(self, filter_tools=None):
        tools = self._get_filtered_tools(filter_tools)
        return self.renderer.render_text(tools)

# 3. Tests (2.5 hours)
def test_tool_renderer():
    ...
```

This gives us:
- ✅ Abstraction in place
- ✅ Easy to extend later
- ✅ No behavioral change
- ✅ Minimal risk

---

## Decision Matrix

| Factor | Implement Now | Wait for llama.cpp |
|--------|---------------|-------------------|
| **Effort** | 6-13 hours | Same (but harder later) |
| **Token savings** | ✅ Immediate (10-20%) | ❌ Delayed |
| **Code quality** | ✅ Better now | ⚠️ Debt accumulates |
| **Risk** | 🟢 Low (additive) | 🟢 Low |
| **Urgency** | 🟡 Medium | 🟢 Low |
| **Value** | 🔴 High | 🔴 High (when ready) |

---

## Recommendation

**Implement Phase 1 Now** (ToolRenderer with text formats)

**Why**:
1. **Effort is reasonable**: ~1 day, not weeks
2. **Immediate benefits**: Token savings, cleaner code
3. **Low risk**: Additive change, fully backward compatible
4. **Future-proof**: Ready for structured calling when llama.cpp ships it
5. **ML engineer specifically called this out** - It's on their radar for a reason

**When to do Phase 2**:
- When llama.cpp adds function calling support, OR
- When we add OpenAI/Anthropic backend support

---

## Sample Output Comparison

### Current Text Manifest (Verbose)
```
Available tools:

web_search: Search the web for current information using DuckDuckGo.
**When to use**: Finding recent news, articles...
**Parameters**: query (str): Natural language search query...
Input schema: {'type': 'object', 'properties': {'query': {'type': 'string'...}}}
Output schema: {'type': 'object', 'properties': {'results': ...}}
Side effects: none

(~450 tokens for 5 tools)
```

### With ToolRenderer (Concise)
```
Available tools:

**web_search**: Search web for current information
  query (string, required): Search query 2-100 chars
  max_results (integer): Max results, default 5

**web_access**: Fetch and extract content from URL
  url (string, required): URL to fetch
  response_format (string): "concise" or "detailed"

(~200 tokens for 5 tools - 56% reduction!)
```

### With Structured Calling (Future)
```python
# No text at all - passed as structured data
tools = [
    {"type": "function", "function": {"name": "web_search", ...}},
    ...
]
# Sent in API payload, not prompt
# Result: Even more token savings
```

---

## Conclusion

**Actual Effort**: 🟡 **MEDIUM** (~1 day for Phase 1)
- Not "large" as initially estimated
- Well-scoped, clear boundaries
- Additive change (low risk)

**Actual Value**: 🔴 **HIGH**
- Immediate token savings
- Cleaner architecture
- Future-proof for structured calling

**Should We Do It?**: ✅ **YES - Phase 1 Now**

The ML engineer was right to call this out. It's a clean abstraction that pays dividends immediately and sets us up for the future. The effort is reasonable (~1 day) for the value gained.

---

**Document Version**: 1.0
**Created**: December 2, 2025
**Recommendation**: Implement Phase 1 (text formats) in next sprint
