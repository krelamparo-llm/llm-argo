# Research Mode Prompt Fix - Root Cause Analysis

**Date**: December 2024
**Issue**: Research mode creates plan but never executes tools or synthesizes

---

## Root Cause Identified

### The Fundamental Problem

**The research mode prompt contradicts itself:**

```
PHASE 1: PLANNING
IMPORTANT: Output ONLY a research plan using this exact format...
```

**This tells the model to output ONLY the plan and stop.** The model is following instructions perfectly - we gave it bad instructions.

### Why Retries Don't Fix This

The retry logic (added earlier) is a **band-aid** that doesn't address the root cause:
- Model outputs plan and stops (as instructed)
- Code detects no tool call, sends weak follow-up prompt
- Model is confused: "You just told me to output ONLY a plan, now you want tools?"
- Even with retries, the underlying instruction conflict remains

---

## The Real Fix: Prompt Architecture

### Change 1: Remove "ONLY" from Phase 1

**Before** (line 273):
```
PHASE 1: PLANNING
IMPORTANT: Output ONLY a research plan using this exact format...
```

**After**:
```
PHASE 1: PLANNING
First, output a research plan using this exact format...

PHASE 2: EXECUTION
**IMMEDIATELY after outputting your research plan**, begin tool execution.
```

**Impact**: Creates a natural flow from plan → execution instead of telling model to stop.

---

### Change 2: Strengthen Follow-Up Prompt

**Before** (line 1138-1140):
```python
prompt_for_tools = (
    "Good! You've created a research plan. Now IMMEDIATELY begin executing your first search.\n\n"
    "Output your FIRST tool call now (no other text)."
)
```

**Problems**:
- No concrete example of tool call format
- No guidance on which query to use
- Vague instruction

**After** (line 1146-1152):
```python
prompt_for_tools = (
    f"RESEARCH PLAN RECEIVED. Now execute PHASE 2: EXECUTION.\n\n"
    f"You MUST output a tool call using this EXACT format:\n\n"
    f"{tool_example}\n\n"  # Shows XML or JSON format with placeholder
    f"Replace 'your first search query from plan' with the FIRST search from your plan's 'Search strategy' section.\n"
    f"Output ONLY the tool call above. NO explanations. STOP immediately after {closing_tag}."
)
```

**Improvements**:
- ✅ Shows exact format (XML or JSON based on model)
- ✅ Tells model WHERE in plan to find query ("Search strategy" section)
- ✅ Explicit stop instruction
- ✅ References "PHASE 2: EXECUTION" from original prompt

---

## Files Modified

| File | Lines | Change |
|------|-------|--------|
| `orchestrator.py` | 273, 295-296 | Remove "ONLY", add "IMMEDIATELY after" |
| `orchestrator.py` | 1136-1155 | Strengthen follow-up prompt with concrete example |
| `orchestrator.py` | 1343-1356 | Retry logic (kept as safety net) |

---

## Why This Should Work

### Before Fix
```
User: "Research Claude vs GPT-4"
↓
[SYSTEM: Output ONLY a plan]
↓
Model: <research_plan>...</research_plan>  [STOPS - as instructed]
↓
[SYSTEM: Now output a tool call]
↓
Model: [confused - you just said ONLY plan]
```

### After Fix
```
User: "Research Claude vs GPT-4"
↓
[SYSTEM: First output plan, IMMEDIATELY after begin execution]
↓
Model: <research_plan>...</research_plan>
       <tool_call>...web_search...</tool_call>  [natural flow]
↓
[If no tool call - SYSTEM: PHASE 2 requires this format: <example>]
↓
Model: <tool_call>...web_search...</tool_call>  [clear instructions]
```

---

## Testing Strategy

### Test 1: Natural Flow (Ideal Case)
Model outputs **both** plan and tool call in single response.

**Expected Log Sequence**:
```
→ "Research plan created"
→ "Executing 1 tools"
→ "Tool execution completed: web_search"
→ (more tools...)
→ "Triggering synthesis phase"
```

### Test 2: Follow-Up Needed (Fallback)
Model outputs only plan, needs follow-up prompt.

**Expected Log Sequence**:
```
→ "Research plan created"
→ "Prompting for tool execution after plan"
→ "Executing 1 tools"
→ "Tool execution completed: web_search"
→ (more tools...)
→ "Triggering synthesis phase"
```

### Test 3: Multiple Retries (Safety Net)
Model still doesn't output tool call after follow-up.

**Expected Log Sequence**:
```
→ "Research plan created"
→ "Prompting for tool execution after plan"
→ "Research mode: no tool call after plan, retrying" (attempt 1)
→ "Research mode: no tool call after plan, retrying" (attempt 2)
→ "Executing 1 tools" (finally works)
```

---

## Comparison: Retry vs Prompt Fix

| Approach | Addresses Root Cause | Success Rate | Latency |
|----------|---------------------|--------------|---------|
| **Retry Logic** | ❌ No - band-aids over bad prompt | Medium | High (3+ LLM calls) |
| **Prompt Fix** | ✅ Yes - removes instruction conflict | High | Low (1-2 LLM calls) |
| **Both Combined** | ✅ Yes + safety net | Highest | Low-Medium |

**Recommendation**: Use both. Prompt fix addresses root cause, retry provides safety net for edge cases.

---

## Alternative Solutions Considered

### Option A: Force Tool Execution
Programmatically extract query from plan and execute without LLM.

**Pros**: Guaranteed execution
**Cons**: Bypasses model's reasoning, hard-coded behavior
**Verdict**: Last resort only

### Option B: Single-Phase Research
Remove planning phase, go straight to tool execution.

**Pros**: Simpler flow
**Cons**: Loses planning benefits (structured queries, quality control)
**Verdict**: Defeats purpose of research mode

### Option C: Few-Shot Examples
Add example research flows to system prompt.

**Pros**: Shows model the full workflow
**Cons**: Token expensive, may not generalize
**Verdict**: Worth trying if prompt fix insufficient

---

## Follow-Up Actions

### Immediate
1. ✅ Test with TEST-004, TEST-005, TEST-011
2. ⏳ Check logs for natural flow (plan + tool call in one response)
3. ⏳ Verify follow-up prompt triggers correctly when needed

### If Still Failing
1. Add diagnostic logging of raw LLM responses
2. Check if `_maybe_parse_plan()` is correctly extracting tool calls
3. Consider few-shot examples in system prompt
4. Test with different models (some handle multi-phase better)

### Long Term
1. Monitor "Prompting for tool execution" frequency
2. If high, add few-shot examples to reduce follow-up needs
3. Consider JSON format (more structured than XML)
4. Add telemetry: "plan-only" vs "plan+tools" response rate

---

## Key Insight

**The problem was never about retries, parsing, or execution logic.**

**The problem was a prompt that said "output ONLY X" then expected the model to continue with Y.**

Models are literal - they follow instructions. If we want them to output plan THEN tools, we need to say:
1. "First output plan"
2. "IMMEDIATELY after, output tools"

Not:
1. "Output ONLY plan"
2. [confused surprise when model stops]
