# CONCISE_TEXT Integration Analysis for QUICK_LOOKUP Mode

**Date**: December 2, 2025
**Question**: Why is this optional? What are the risks/tradeoffs of implementing now?

---

## Current State

### What We Have
- ✅ CONCISE_TEXT format implemented and tested
- ✅ 84.3% token savings validated (810 chars → 127 chars)
- ✅ ToolRegistry supports format parameter
- ❌ Orchestrator still uses hardcoded tool examples in mode prompts

### Where Tools Are Currently Described

**Location**: [orchestrator.py:344-354](argo_brain/argo_brain/assistant/orchestrator.py#L344-L354)

```python
TOOL USAGE GUIDELINES:
- **Maximum**: 1 tool call per query (strictly enforced)
- **Prefer memory_query** - Check if we've researched this before (faster than web search)
- **Use web_search** - If topic is completely new or requires current information
- **Format**: JSON
- **DO NOT SAY "I need to search"** - Just output the tool call

WHEN TO USE TOOLS:
✓ Context doesn't contain the answer → OUTPUT web_search tool call
✓ User asks about current/recent events (2024-2025) → OUTPUT web_search tool call
✓ Technical details not in knowledge base → OUTPUT web_search tool call
✓ Questions about specific versions, latest releases, recent news → OUTPUT web_search tool call
```

**Problem**:
- Tool names are hardcoded as prose ("prefer memory_query", "use web_search")
- No formal tool manifest with parameters
- Relies on model's pre-training knowledge of what these tools do

---

## Why It's Currently "Optional"

### Reason 1: Architectural Philosophy

From [ML_ENGINEER_FEEDBACK_EVALUATION.md:153-157](docs/ML_ENGINEER_FEEDBACK_EVALUATION.md#L153-L157):

> **Priority**: 🟢 **LOW** - We only support one model currently
>
> **Recommendation**:
> - **Now**: Keep in code, we're iterating fast
> - **When adding second model**: Refactor to config-driven approach

**Translation**: We intentionally deferred dynamic tool manifests until we need multi-model support. The current hardcoded approach works and is fast to iterate on.

### Reason 2: Uncertainty About Model Behavior

**Unknown**: How will Qwen3-Coder-30B handle ultra-concise tool descriptions?

Current prompts are verbose and prescriptive:
```
- **Prefer memory_query** - Check if we've researched this before (faster than web search)
- **Use web_search** - If topic is completely new or requires current information
```

CONCISE_TEXT would be:
```
Tools: memory_query(query:str), web_search(query:str, max_results?:int)
```

**Question**: Will the model understand WHEN to use each tool without the prose guidance?

### Reason 3: No Urgent Need

**Current token budget for QUICK_LOOKUP**:
- Mode prompt: ~370 lines (estimated ~2500 tokens with examples)
- Max tokens for response: 1024
- Total context: Plenty of headroom

**Token pressure**: None currently. The 84% savings is nice but not critical.

---

## Risks of Implementing Now

### Risk 1: Model Confusion (MEDIUM)

**Risk**: Model may not understand tool purposes without descriptive prose

**Evidence Against This Risk**:
- Modern LLMs are trained on function signatures
- Tool names are self-descriptive: `web_search`, `memory_query`, `web_access`
- JSON schema includes parameter descriptions
- Model has seen similar patterns in training data

**Evidence For This Risk**:
- Current prompts heavily scaffold the model ("prefer X", "use Y when Z")
- We had to add "CRITICAL INSTRUCTION" to force tool calls in QUICK_LOOKUP
- Model may default to "I would need to search" without explicit guidance

**Mitigation**:
```python
# Hybrid approach: CONCISE_TEXT + prose guidance
available_tools = ["web_search", "memory_query"]
tool_manifest = tool_registry.manifest(
    filter_tools=available_tools,
    format=ToolFormat.CONCISE_TEXT
)

# Still provide usage guidance, but reference the manifest
prompt = f"""You are in QUICK LOOKUP mode...

{tool_manifest}

TOOL USAGE GUIDELINES:
- **Prefer memory_query** - Check if we've researched this before
- **Use web_search** - If topic requires current information
...
"""
```

**Severity**: 🟡 MEDIUM - Could break QUICK_LOOKUP reliability
**Likelihood**: 🟢 LOW - Modern models handle function signatures well

---

### Risk 2: Regression in Tool Call Quality (LOW-MEDIUM)

**Risk**: Model might make less appropriate tool choices without prose guidance

**Current approach** (prescriptive):
```
WHEN TO USE TOOLS:
✓ Context doesn't contain the answer → OUTPUT web_search tool call
✓ User asks about current/recent events (2024-2025) → OUTPUT web_search tool call
```

**CONCISE_TEXT approach** (minimalist):
```
Tools: web_search(query:str, max_results?:int), memory_query(query:str)
```

**Test Case**: User asks "What's the capital of France?"
- **With prose guidance**: Model sees "Context doesn't contain the answer → OUTPUT web_search"
- **With CONCISE_TEXT only**: Model might just answer from training data (correct!)
- **Actual risk**: None for this case

**Test Case**: User asks "What's the latest Claude model?"
- **With prose guidance**: Model sees "User asks about current/recent events → OUTPUT web_search"
- **With CONCISE_TEXT only**: Model still knows this requires current info
- **Actual risk**: Low - model understands temporal requirements

**Severity**: 🟡 MEDIUM - Could reduce tool call appropriateness
**Likelihood**: 🟢 LOW - Tool names + param descriptions provide sufficient context

---

### Risk 3: Breaking Existing Test Suite (HIGH - But Easily Mitigated)

**Risk**: Test suite #1 expects specific prompt structure

From previous conversation:
> "test suite #1 failed: User: What's the latest Claude model from Anthropic? [Model didn't make tool call]"

We fixed this by adding:
```python
CRITICAL INSTRUCTION: If you don't have the answer in your training data or the provided context,
you MUST make a tool call. Do NOT say "I would need to search" - ACTUALLY SEARCH
```

**If we replace prose with CONCISE_TEXT**:
- This critical instruction might not be sufficient
- Model might need explicit "WHEN TO USE" examples
- Tests could fail again

**Mitigation**: Keep the critical instruction + usage examples, just add CONCISE_TEXT manifest

**Severity**: 🔴 HIGH - Would break validated tests
**Likelihood**: 🔴 HIGH - Removing prose guidance will likely regress

**Solution**: Hybrid approach (see below)

---

### Risk 4: Premature Optimization (LOW)

**Risk**: Optimizing for token savings when we don't have token pressure

**Current reality**:
- QUICK_LOOKUP max_tokens: 1024
- Prompt size: ~2500 tokens (estimated)
- Total: ~3500 tokens
- Model context: 32K+ tokens available
- **Token pressure**: NONE

**Is the 84% savings meaningful?**
- Saves ~680 tokens on tool manifest
- In a 32K context budget: 2.1% savings
- **Impact**: Negligible

**However**:
- Cleaner prompts are easier to maintain
- Reducing clutter helps model focus
- Sets pattern for future token-constrained scenarios

**Verdict**: Not urgent, but not harmful either

**Severity**: 🟢 LOW - Not a problem
**Likelihood**: 🟢 N/A - This is a philosophy question

---

## Tradeoffs of Implementing Now

### ✅ PROS

1. **Token Savings Available Immediately**
   - 84.3% reduction on tool manifest section
   - ~680 tokens saved per QUICK_LOOKUP query
   - Cleaner, more focused prompts

2. **Consistency with Architecture**
   - Separates tool *availability* (manifest) from tool *guidance* (prose)
   - Follows separation of concerns principle
   - Aligns with ML engineer's recommendation for tool abstraction

3. **Easier Testing**
   - Can test tool manifest rendering independently
   - Can validate all 5 tools are correctly described
   - Can verify filtering works correctly

4. **Learning Opportunity**
   - See how model handles concise vs verbose tool descriptions
   - Gather data for future multi-model support
   - Validate ToolRenderer in production

5. **Low Implementation Cost**
   - ~10 lines of code to add to orchestrator
   - Fully backward compatible (can revert easily)
   - Tests already written and passing

### ❌ CONS

1. **Risk of Model Confusion**
   - Model might not understand tool purposes without prose
   - Could break QUICK_LOOKUP reliability
   - Would require debugging and prompt tuning

2. **Risk of Test Regressions**
   - Current tests expect prescriptive prompts
   - CONCISE_TEXT might not trigger tool calls appropriately
   - Would need to validate all test cases pass

3. **No Clear Need**
   - Token pressure is low (32K context available)
   - Current approach works well
   - Savings are nice but not critical

4. **Added Complexity**
   - One more abstraction layer
   - One more place to debug if things break
   - Slightly harder to trace prompt assembly

5. **Unvalidated Assumption**
   - Assumes Qwen3-Coder-30B handles concise manifests well
   - Haven't tested model behavior with minimal tool descriptions
   - Could discover model needs more scaffolding

---

## Recommended Approach: HYBRID (Best of Both Worlds)

### Option A: CONCISE_TEXT + Prose Guidance

**Idea**: Use CONCISE_TEXT for formal tool definitions, keep prose for usage guidance

```python
def _get_default_quick_lookup_prompt(self) -> str:
    # Get available tools for this mode
    available_tools = ["web_search", "memory_query", "web_access", "retrieve_context"]

    # Render concise tool manifest
    tool_manifest = self.tool_registry.manifest(
        filter_tools=available_tools,
        format=ToolFormat.CONCISE_TEXT
    )

    return f"""You are in QUICK LOOKUP mode: provide fast, concise answers with minimal tool usage.

CRITICAL INSTRUCTION: If you don't have the answer in your training data or the provided context,
you MUST make a tool call. Do NOT say "I would need to search" - ACTUALLY SEARCH

AVAILABLE TOOLS:
{tool_manifest}

TOOL USAGE GUIDELINES:
- **Prefer memory_query** - Check if we've researched this before (faster than web search)
- **Use web_search** - If topic is completely new or requires current information
- **Use web_access** - If you have a specific URL to fetch
- **Use retrieve_context** - Search knowledge base for relevant documents

WHEN TO USE TOOLS:
✓ Context doesn't contain the answer → OUTPUT tool call
✓ User asks about current/recent events → OUTPUT web_search
✓ Technical details not in knowledge base → OUTPUT web_search
...
"""
```

**Benefits**:
- ✅ Formal tool definitions (clean, validated)
- ✅ Prose guidance preserved (safe, tested)
- ✅ Token savings (~400 chars vs current)
- ✅ Low risk of regression

**Tradeoff**: Still verbose, but more structured

---

### Option B: CONCISE_TEXT Only (Aggressive)

**Idea**: Replace all hardcoded tool references with dynamic manifest, minimal prose

```python
def _get_default_quick_lookup_prompt(self) -> str:
    available_tools = ["web_search", "memory_query"]
    tool_manifest = self.tool_registry.manifest(
        filter_tools=available_tools,
        format=ToolFormat.CONCISE_TEXT
    )

    return f"""You are in QUICK LOOKUP mode: provide fast, concise answers with minimal tool usage.

{tool_manifest}

RULES:
1. If you don't have the answer, make a tool call (don't explain, just do it)
2. Maximum 1 tool call per query
3. Provide direct answer after tool result

Format: {tool_format_label}
"""
```

**Benefits**:
- ✅ Maximum token savings (84% on tools + reduced prose)
- ✅ Cleaner, simpler prompt
- ✅ Tests model's ability to infer tool usage

**Risks**:
- ❌ HIGH risk of test regressions
- ❌ Model might not call tools appropriately
- ❌ Would need significant validation

**Verdict**: Too risky without testing

---

### Option C: Staged Rollout (RECOMMENDED)

**Phase 1: Add CONCISE_TEXT to Research Mode First**

Why RESEARCH mode?
- Already has comprehensive scaffolding
- Tool calls happen after planning phase (less risk)
- Phase-based temperature already working well
- Lower risk test case

```python
# In _get_default_research_prompt()
if research_stats.get("has_plan"):
    available_tools = self._get_available_tools_for_mode(SessionMode.RESEARCH, research_stats)
    tool_manifest = self.tool_registry.manifest(
        filter_tools=available_tools,
        format=ToolFormat.TEXT_MANIFEST  # Start with verbose for safety
    )
    # Inject manifest into prompt
```

**Phase 2: Switch RESEARCH to CONCISE_TEXT (After Validation)**

```python
format=ToolFormat.CONCISE_TEXT  # After seeing it works in research mode
```

**Phase 3: Add to QUICK_LOOKUP (After RESEARCH Success)**

Only after we've validated:
- Model understands concise tool descriptions
- Tool calls are appropriate
- No regressions in quality

**Benefits**:
- ✅ Lowest risk approach
- ✅ Learn from RESEARCH mode first
- ✅ Validate assumptions before touching QUICK_LOOKUP
- ✅ Easy to rollback at each phase

---

## Decision Matrix

| Approach | Token Savings | Risk | Effort | Recommendation |
|----------|---------------|------|--------|----------------|
| **Do Nothing** | 0% | 🟢 None | 0 hours | ❌ Misses learning opportunity |
| **Hybrid (A)** | ~50% | 🟡 Low | 1 hour | ✅ **RECOMMENDED** - Safe, structured |
| **Concise Only (B)** | 84% | 🔴 High | 2 hours + testing | ❌ Too risky without validation |
| **Staged (C)** | Progressive | 🟢 Low | 3 hours over time | ✅ **RECOMMENDED** - Lowest risk |

---

## Why It's "Optional" - Summary

### It's optional because:

1. **No urgent need** - Token pressure is low, current approach works
2. **Unvalidated assumption** - Haven't tested model behavior with concise descriptions
3. **Risk of regression** - Could break carefully-tuned QUICK_LOOKUP prompts
4. **Philosophy alignment** - ML engineer recommended deferring dynamic manifests until multi-model support
5. **Fast iteration** - Keeping things in code allows quicker experimentation

### It's NOT optional because:

1. **Technical debt** - Hardcoded tool names should be in manifest
2. **Cleaner architecture** - Separation of concerns (manifest vs guidance)
3. **Token efficiency** - 84% savings is significant even if not critical
4. **Future-proofing** - Sets pattern for multi-model support
5. **Learning opportunity** - Gather data on model behavior with minimal scaffolding

---

## Recommended Action

### IMPLEMENT HYBRID APPROACH (Option A) NOW

**Why**:
- Low risk (preserves prose guidance)
- Moderate token savings (~50%)
- Validates ToolRenderer in production
- Maintains test suite compatibility
- Easy to rollback if issues arise

**Changes Required**:
1. Update `_get_default_quick_lookup_prompt()` to inject CONCISE_TEXT manifest
2. Keep all usage guidelines and critical instructions
3. Update `_get_available_tools_for_mode()` call to happen in prompt generation
4. Run test suite #1 to validate no regressions

**Effort**: ~1 hour

**Risk**: 🟢 LOW

---

### ALTERNATIVE: STAGED ROLLOUT (Option C)

**Why**:
- Lowest risk approach
- Learn from RESEARCH mode first
- Gather data before touching QUICK_LOOKUP
- Validate assumptions incrementally

**Timeline**:
- Week 1: Add dynamic manifest to RESEARCH mode (TEXT_MANIFEST format)
- Week 2: Switch RESEARCH to CONCISE_TEXT, monitor quality
- Week 3: If successful, add to QUICK_LOOKUP (hybrid first)
- Week 4: If successful, consider pure CONCISE_TEXT

**Effort**: ~3 hours spread over 4 weeks

**Risk**: 🟢 VERY LOW

---

## Conclusion

**Why it's optional**:
- Works without it (no urgent need)
- Unvalidated assumptions (model behavior unknown)
- Risk of regression (tests carefully tuned)
- Philosophy alignment (deferred until multi-model)

**Why you should do it anyway**:
- Cleaner architecture (separation of concerns)
- Moderate token savings (~50% hybrid, 84% aggressive)
- Validates ToolRenderer in production
- Low risk with hybrid approach
- Sets pattern for future

**Recommended**: **Hybrid approach (Option A)** - formal tool definitions + prose guidance

**Alternative**: **Staged rollout (Option C)** - validate in RESEARCH mode first

**Not Recommended**: Pure CONCISE_TEXT without validation (too risky)

---

**Document Version**: 1.0
**Created**: December 2, 2025
**Recommendation**: Implement Hybrid Approach (low risk, moderate value)
