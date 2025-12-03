# ToolRenderer Phase 2 Integration TODOs

**Date**: December 2, 2025
**Status**: 📋 **PLANNED** (not started)
**Trigger**: When adding second model OR when token pressure becomes an issue

---

## Phase 1 Status: ✅ COMPLETE

What we have now:
- ✅ `tools/renderer.py` with 5 formats implemented
- ✅ `ToolRegistry.manifest()` accepts format parameter
- ✅ 19 tests, all passing
- ✅ 84.3% token savings validated for CONCISE_TEXT
- ✅ Backward compatible (defaults to TEXT_MANIFEST)

What we DON'T have:
- ❌ Orchestrator integration (still uses hardcoded tool examples)
- ❌ Dynamic tool manifest injection
- ❌ Config-driven format selection
- ❌ Production validation of CONCISE_TEXT

---

## Phase 2: Integration with Orchestrator

### When to Start Phase 2

**Triggers** (any of these):
1. Adding a second model to the system
2. Token budget becomes constrained
3. Need to support OpenAI/Anthropic backends
4. llama.cpp adds function calling support
5. Want cleaner, more maintainable prompts

**Priority**: 🟡 MEDIUM (not urgent, but valuable)

---

## TODO 1: Add Dynamic Tool Manifests to Mode Prompts

### Current State

**Location**: [orchestrator.py:344-354](argo_brain/argo_brain/assistant/orchestrator.py#L344-L354)

Tool names are hardcoded in prose:
```python
TOOL USAGE GUIDELINES:
- **Prefer memory_query** - Check if we've researched this before
- **Use web_search** - If topic is completely new or requires current information
```

### Target State (Hybrid Approach - RECOMMENDED)

```python
def _get_default_quick_lookup_prompt(self) -> str:
    """Generate default quick lookup mode prompt with dynamic tool manifest."""

    # Get available tools for this mode
    available_tools = self._get_available_tools_for_mode(
        SessionMode.QUICK_LOOKUP,
        research_stats={}
    )

    # Determine format based on mode and config
    tool_format = self._get_tool_format_for_mode(SessionMode.QUICK_LOOKUP)

    # Render tool manifest dynamically
    tool_manifest = self.tool_registry.manifest(
        filter_tools=available_tools,
        format=tool_format
    )

    # Build format-specific instructions
    if self.use_xml_format:
        tool_format_example = """<tool_call>
<function=web_search>
<parameter=query>your search query here</parameter>
</function>
</tool_call>"""
        tool_format_label = "XML"
    else:
        tool_format_example = '<tool_call>\n{"name": "web_search", "arguments": {"query": "your search query"}}\n</tool_call>'
        tool_format_label = "JSON"

    return f"""You are in QUICK LOOKUP mode: provide fast, concise answers with minimal tool usage.

CRITICAL INSTRUCTION: If you don't have the answer in your training data or the provided context,
you MUST make a tool call. Do NOT say "I would need to search" - ACTUALLY SEARCH

AVAILABLE TOOLS:
{tool_manifest}

TOOL USAGE GUIDELINES:
- **Prefer memory_query** - Check if we've researched this before (faster than web search)
- **Use web_search** - If topic is completely new or requires current information
- **Format**: {tool_format_label}

WHEN TO USE TOOLS:
✓ Context doesn't contain the answer → OUTPUT tool call
✓ User asks about current/recent events → OUTPUT web_search
...
"""
```

### Implementation Steps

**File**: `argo_brain/argo_brain/assistant/orchestrator.py`

1. **Add helper method** (~10 lines):
   ```python
   def _get_tool_format_for_mode(self, session_mode: SessionMode) -> ToolFormat:
       """Determine tool format based on mode and model config.

       Args:
           session_mode: Current session mode

       Returns:
           ToolFormat to use for this mode
       """
       # For QUICK_LOOKUP: use CONCISE_TEXT for token efficiency
       if session_mode == SessionMode.QUICK_LOOKUP:
           return ToolFormat.CONCISE_TEXT

       # For RESEARCH/INGEST: use TEXT_MANIFEST for comprehensive descriptions
       elif session_mode in (SessionMode.RESEARCH, SessionMode.INGEST):
           return ToolFormat.TEXT_MANIFEST

       # Future: check ModelPromptConfig for per-model preferences
       # if hasattr(self, "prompt_config") and self.prompt_config:
       #     return ToolFormat(self.prompt_config.tool_calling.manifest_format)

       return ToolFormat.TEXT_MANIFEST  # Default
   ```

2. **Update `_get_default_quick_lookup_prompt()`** (~20 lines modified):
   - Call `_get_available_tools_for_mode()` at top
   - Call `_get_tool_format_for_mode()` to determine format
   - Call `self.tool_registry.manifest()` with filter and format
   - Inject `{tool_manifest}` into prompt template
   - Keep all usage guidelines (hybrid approach)

3. **Update `_get_default_research_prompt()`** (~25 lines modified):
   - Similar pattern as QUICK_LOOKUP
   - Use TEXT_MANIFEST format (comprehensive descriptions)
   - Inject manifest after "MANDATORY TOOL USAGE" section

4. **Update `_get_default_ingest_prompt()`** (~15 lines modified):
   - Similar pattern
   - Use TEXT_MANIFEST format

**Effort**: 2-3 hours

**Risk**: 🟡 MEDIUM - Could affect prompt behavior

**Testing Required**:
- Run test suite #1 (QUICK_LOOKUP tool calling)
- Validate RESEARCH mode still works
- Check INGEST mode behavior
- Compare token usage before/after

---

## TODO 2: Add Tool Format to ModelPromptConfig YAML Schema

### Current YAML Structure

**File**: `argo_prompts.yaml`

```yaml
tool_calling:
  format: "xml"  # or "json"
  supports_parallel_calls: false
  stop_sequences: ["</tool_call>", "<|im_end|>"]
```

### Target YAML Structure

```yaml
tool_calling:
  format: "xml"  # Tool call format (xml/json)
  supports_parallel_calls: false
  stop_sequences: ["</tool_call>", "<|im_end|>"]
  manifest_format: "text_manifest"  # NEW: Tool manifest format
  # Options: text_manifest, qwen_xml, concise_text, openai_tools, anthropic_tools

modes:
  quick_lookup:
    preamble: "..."
    manifest_format: "concise_text"  # Override for specific mode

  research:
    preamble: "..."
    manifest_format: "text_manifest"  # Comprehensive for research

  ingest:
    preamble: "..."
    manifest_format: "text_manifest"
```

### Implementation Steps

1. **Update `ModelPromptConfig` dataclass** in `argo_brain/model_prompts.py`:
   ```python
   @dataclass
   class ToolCallingConfig:
       format: str  # xml, json
       supports_parallel_calls: bool
       stop_sequences: List[str]
       manifest_format: str = "text_manifest"  # NEW

   @dataclass
   class ModeConfig:
       preamble: str
       max_tool_calls: Optional[int] = None
       manifest_format: Optional[str] = None  # NEW: per-mode override
   ```

2. **Update YAML loading** to parse new fields

3. **Update `_get_tool_format_for_mode()`** to check config:
   ```python
   def _get_tool_format_for_mode(self, session_mode: SessionMode) -> ToolFormat:
       # Check mode-specific override first
       if hasattr(self, "prompt_config") and self.prompt_config:
           mode_name = session_mode.value
           if mode_name in self.prompt_config.modes:
               mode_config = self.prompt_config.modes[mode_name]
               if mode_config.manifest_format:
                   return ToolFormat(mode_config.manifest_format)

           # Fall back to global config
           if self.prompt_config.tool_calling.manifest_format:
               return ToolFormat(self.prompt_config.tool_calling.manifest_format)

       # Final fallback
       return ToolFormat.TEXT_MANIFEST
   ```

**Effort**: 2 hours

**Risk**: 🟢 LOW - Additive change

---

## TODO 3: Validate Token Savings in Production

### Objective

Measure actual token savings and verify no quality degradation.

### Metrics to Track

1. **Token Usage**:
   - Prompt tokens before/after (per mode)
   - Response tokens (unchanged expected)
   - Total tokens per query

2. **Quality Metrics**:
   - Tool call accuracy (did model call the right tool?)
   - Tool call necessity (did model call when needed?)
   - Response quality (subjective, sample-based)

3. **Performance**:
   - Latency (prompt generation time - should be negligible)
   - Model inference time (unchanged expected)

### Implementation

**File**: `argo_brain/argo_brain/assistant/orchestrator.py`

Add logging to track token usage:

```python
def send_message(self, session_id: str, user_message: str) -> AssistantResponse:
    # ... existing code ...

    # Before LLM call
    prompt_text = "\n".join(m.content for m in messages)
    prompt_tokens_estimate = len(prompt_text) // 4  # Rough estimate

    self.logger.info(
        "Prompt assembled with dynamic tool manifest",
        extra={
            "session_mode": active_mode.value,
            "tool_format": tool_format.value,
            "prompt_tokens_estimate": prompt_tokens_estimate,
            "tools_available": len(available_tools),
        }
    )

    # ... existing LLM call ...
```

### Validation Checklist

- [ ] Run 50 QUICK_LOOKUP queries with CONCISE_TEXT
- [ ] Compare token usage vs baseline (current hardcoded)
- [ ] Check tool call accuracy (should be ≥95%)
- [ ] Check response quality (sample 10 queries, subjective)
- [ ] Monitor for "I would need to search" regressions
- [ ] Validate test suite #1 still passes

**Effort**: 4-6 hours (includes monitoring and analysis)

**Risk**: 🟡 MEDIUM - Production validation required

---

## TODO 4: Support Structured Function Calling (Future)

### Trigger

When llama.cpp adds native function calling support OR when adding OpenAI/Anthropic backends.

### Current Flow

```
Orchestrator → Text manifest in prompt → LLM → Parse XML/JSON from response
```

### Target Flow (Structured Calling)

```
Orchestrator → Structured tool defs in API call → LLM → Structured tool calls in response
```

### Implementation Steps

1. **Add `supports_function_calling` to LLMClient**:
   ```python
   class LLMClient:
       @property
       def supports_function_calling(self) -> bool:
           """Check if backend supports native function calling."""
           # For llama.cpp: check server capabilities
           # For OpenAI: always True
           # For Anthropic: always True
           return False  # Current: not supported
   ```

2. **Update `LLMClient.chat()` to accept tools parameter**:
   ```python
   def chat(
       self,
       messages: List[ChatMessage],
       temperature: float = 0.7,
       max_tokens: int = 512,
       tools: Optional[List[Dict]] = None,  # NEW
   ) -> ChatResponse:
       if tools and self.supports_function_calling:
           # Send tools in API payload (OpenAI/Anthropic format)
           payload["tools"] = tools
       # ... existing code ...
   ```

3. **Update orchestrator to conditionally use structured calling**:
   ```python
   # In send_message()
   if self.llm_client.supports_function_calling:
       # Use structured function calling (preferred)
       tool_defs = self.tool_registry.manifest(
           filter_tools=available_tools,
           format=ToolFormat.OPENAI_TOOLS  # or ANTHROPIC_TOOLS
       )
       response = self.llm_client.chat(
           messages,
           temperature=temperature,
           max_tokens=max_tokens,
           tools=tool_defs,  # ← Structured tools
       )
   else:
       # Fallback to text manifest
       manifest_text = self.tool_registry.manifest(
           filter_tools=available_tools,
           format=tool_format
       )
       messages.append(ChatMessage(role="system", content=manifest_text))
       response = self.llm_client.chat(messages, temperature, max_tokens)
   ```

4. **Update tool call parsing to handle structured responses**:
   ```python
   if response.tool_calls:  # Structured format
       # Model returned structured tool calls
       for tc in response.tool_calls:
           tool_name = tc.function.name
           tool_args = tc.function.arguments
           # Execute directly, no parsing needed
   else:  # Text format
       # Fall back to XML/JSON parsing
       tool_calls = self._extract_tool_calls(response.text)
   ```

**Effort**: 6-8 hours

**Risk**: 🔴 HIGH - Major change, thorough testing required

**Dependencies**: llama.cpp function calling support (not available yet)

---

## TODO 5: Multi-Model Format Testing

### Objective

When we add a second model, validate that ToolRenderer works correctly for both models.

### Test Cases

**Model A**: Qwen3-Coder-30B (current)
- Tool format: XML
- Manifest format: TEXT_MANIFEST (baseline)
- Test with: CONCISE_TEXT (optimized)

**Model B**: (Future - e.g., DeepSeek, Llama, etc.)
- Tool format: JSON
- Manifest format: QWEN_XML (if XML-aware) OR CONCISE_TEXT
- Validate: Tool call accuracy, response quality

### Implementation

1. **Create comparison test suite**:
   ```python
   # tests/test_multi_model_tool_rendering.py

   @pytest.mark.parametrize("model,manifest_format", [
       ("qwen3-coder-30b", ToolFormat.TEXT_MANIFEST),
       ("qwen3-coder-30b", ToolFormat.CONCISE_TEXT),
       ("qwen3-coder-30b", ToolFormat.QWEN_XML),
       ("deepseek-coder-v2", ToolFormat.TEXT_MANIFEST),
       ("deepseek-coder-v2", ToolFormat.CONCISE_TEXT),
   ])
   def test_model_manifest_format_compatibility(model, manifest_format):
       # Test that model + format combination works
       pass
   ```

2. **Document format preferences per model**:
   ```yaml
   # argo_prompts.yaml (per-model configs)

   qwen3-coder-30b:
     tool_calling:
       manifest_format: "concise_text"  # Proven to work well

   deepseek-coder-v2:
     tool_calling:
       manifest_format: "text_manifest"  # Conservative default
   ```

**Effort**: 4-6 hours (when second model added)

**Risk**: 🟡 MEDIUM - Depends on model capabilities

---

## Phase 2 Summary: Effort and Timeline

### Total Effort Estimate

| TODO | Description | Effort | Risk | Priority |
|------|-------------|--------|------|----------|
| TODO 1 | Dynamic tool manifests in prompts | 2-3 hours | 🟡 Medium | High |
| TODO 2 | YAML schema extension | 2 hours | 🟢 Low | Medium |
| TODO 3 | Production validation | 4-6 hours | 🟡 Medium | High |
| TODO 4 | Structured function calling | 6-8 hours | 🔴 High | Low (future) |
| TODO 5 | Multi-model testing | 4-6 hours | 🟡 Medium | Medium |
| **Total (Required)** | TODOs 1-3 | **8-11 hours** | | **~2 days** |
| **Total (Optional)** | TODOs 4-5 | **10-14 hours** | | **When needed** |

### Recommended Timeline

**When to Start**: When any of these triggers occur:
1. Adding a second model to the system
2. Token budget becomes constrained
3. Want to clean up hardcoded tool references
4. llama.cpp adds function calling support

**Phased Approach** (Recommended):

**Week 1**: TODO 1 + 2 (Foundation)
- Add dynamic manifests to orchestrator
- Extend YAML schema
- Use TEXT_MANIFEST format initially (safe)

**Week 2**: TODO 3 (Validation)
- Switch to CONCISE_TEXT for QUICK_LOOKUP
- Monitor token usage and quality
- Validate no regressions

**Week 3**: Evaluate and decide on TODO 4/5
- If second model added: proceed with TODO 5
- If function calling available: proceed with TODO 4
- Otherwise: hold and monitor

---

## Quick Reference: When to Do What

### Do Now (Already Done ✅)
- ✅ Implement ToolRenderer
- ✅ Add format parameter to ToolRegistry
- ✅ Write comprehensive tests
- ✅ Document architecture and TODOs

### Do When Adding Second Model
- TODO 1: Dynamic manifests
- TODO 2: YAML schema
- TODO 3: Production validation
- TODO 5: Multi-model testing

### Do When Token Budget Tight
- TODO 1: Dynamic manifests (with CONCISE_TEXT)
- TODO 3: Production validation

### Do When Function Calling Available
- TODO 4: Structured function calling

### Don't Do Yet
- ❌ Integration with orchestrator (wait for trigger)
- ❌ Switching to CONCISE_TEXT (unvalidated)
- ❌ Structured calling (not supported by llama.cpp)

---

## Risk Mitigation Strategies

### For TODO 1 (Dynamic Manifests)

**Risk**: Breaking QUICK_LOOKUP tool calling

**Mitigation**:
1. Start with TEXT_MANIFEST (same as current, just dynamic)
2. Keep all prose guidance intact (hybrid approach)
3. Run test suite #1 before switching to CONCISE_TEXT
4. Have rollback plan (revert to hardcoded if needed)

### For TODO 3 (Production Validation)

**Risk**: Quality degradation not caught in testing

**Mitigation**:
1. A/B test: 50% hardcoded, 50% CONCISE_TEXT
2. Monitor metrics for both groups
3. Only switch to 100% CONCISE_TEXT after validation
4. Keep TEXT_MANIFEST as fallback option

### For TODO 4 (Structured Calling)

**Risk**: Major refactoring breaks existing functionality

**Mitigation**:
1. Implement as opt-in feature (conditional on backend support)
2. Keep text manifest as fallback path
3. Comprehensive integration tests
4. Gradual rollout (research mode → quick_lookup)

---

## Success Criteria

Phase 2 is successful when:

- [ ] All mode prompts use dynamic tool manifests (not hardcoded)
- [ ] CONCISE_TEXT validated in production for QUICK_LOOKUP
- [ ] Token savings measured and documented
- [ ] No regressions in tool call quality
- [ ] Test suite #1 still passes
- [ ] Architecture supports multiple models (when needed)
- [ ] Structured calling ready (when backend supports it)

---

## Notes and Lessons Learned (To Be Updated)

This section will be updated as Phase 2 is implemented.

**Future Notes**:
- What worked well?
- What didn't work as expected?
- Actual vs estimated effort?
- Quality impact observed?
- Token savings in production?
- Model behavior with CONCISE_TEXT?

---

**Document Version**: 1.0
**Created**: December 2, 2025
**Status**: Planning document for future work
**Next Review**: When adding second model or if token budget becomes constrained
