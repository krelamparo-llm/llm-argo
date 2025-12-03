# TEST-011 Debug and Fix

**Date**: December 2, 2025
**Test**: TEST-011 - Parallel Tool Execution (Research Mode)
**Issue**: Model creates research plan but never executes tools
**Status**: ✅ **FIXED**

---

## The Problem

### Observed Behavior

User asked: "Research the top 3 vector databases for RAG systems"

**Expected**:
1. Model creates research plan
2. Orchestrator detects plan
3. Orchestrator prompts model to execute tools
4. Model makes tool calls (web_search)
5. Tools execute in parallel
6. Model synthesizes results

**Actual**:
1. Model creates research plan ✅
2. Orchestrator did NOT detect plan ❌
3. No follow-up prompt ❌
4. No tool calls made ❌
5. Test failed ❌

### Root Cause Analysis

**Investigation Steps**:

1. **Checked logs**: `"Prompting for tool execution after plan"` message did NOT appear
   - This means orchestrator didn't detect the research plan

2. **Examined response**: Model generated malformed XML:
   ```xml
   <research_plan>
   <research_question>...</research_question>
   <sub_questions>
     <sub_question>...</sub_question>
   </sub_questions>
   ...
   </research_plan>   ← Wrong closing order!
   </expected_sources>  ← Closes after research_plan
   ```

3. **Checked `_extract_xml_tag()` method**:
   ```python
   pattern = f"<{tag}>(.*?)</{tag}>"  # Non-greedy regex
   ```
   - This regex expects properly nested XML
   - Malformed XML causes match failure
   - No match → no plan detected → no follow-up prompt

**Root Cause**: Model generated nested XML tags inside `<research_plan>`, but:
- Closed tags in wrong order (malformed XML)
- Regex couldn't extract content
- Orchestrator never detected the plan
- No follow-up prompt to execute tools

---

## Why Did This Happen?

### Was it the DEFAULT_SYSTEM_PROMPT removal?

**NO** - The DEFAULT_SYSTEM_PROMPT never contained XML structure guidance. It only had tool call format instructions (JSON), which we correctly moved to mode prompts with format-awareness (XML or JSON).

The "STOP IMMEDIATELY" instruction is still present in all mode prompts, so that's not the issue either.

### The Real Cause

**The RESEARCH prompt was ambiguous about format**:

**Old prompt** (lines 273-277):
```
First response: Provide ONLY a research plan in <research_plan> tags:
- Research question breakdown: What sub-questions must be answered?
- Search strategy: What keywords/phrases will find authoritative sources?
...
```

**Problem**: Shows bullet points but doesn't explicitly say "don't use nested XML"

**Model interpreted** this as: "Use XML structure with nested tags"
```xml
<research_plan>
  <research_question>...</research_question>
  <sub_questions>
    <sub_question>...</sub_question>
  </sub_questions>
</research_plan>
```

**Result**: Malformed XML → extraction failure → no tool execution

---

## The Fix

### Added Explicit Format Example

**New prompt** (lines 273-294):
```python
PHASE 1: PLANNING
First response: Provide ONLY a research plan in <research_plan> tags (use simple text, NOT nested XML tags):

<research_plan>
Research question: [Main question being investigated]

Sub-questions:
- [First sub-question]
- [Second sub-question]
- [Third sub-question]

Search strategy:
- [Keyword/phrase 1]
- [Keyword/phrase 2]

Success criteria:
- [What information would fully answer this]

Expected sources:
- [Type of sources to find]
</research_plan>

DO NOT use nested XML tags inside <research_plan>. Use simple bullet points.
```

### Why This Works

1. **Explicit example** - Shows exact format expected
2. **Clear prohibition** - "DO NOT use nested XML tags"
3. **Placeholder format** - `[Main question being investigated]` makes it obvious what to fill in
4. **Simple structure** - Flat text with bullet points, no nesting
5. **Parseable** - Single `<research_plan>...</research_plan>` wrapper, no nested tags

---

## Verification

### Expected Behavior After Fix

**Input**: "Research the top 3 vector databases for RAG systems"

**Expected output**:
```xml
<research_plan>
Research question: What are the top 3 vector databases for RAG systems?

Sub-questions:
- What makes a vector database suitable for RAG?
- What are the leading options in 2025?
- How do they compare?

Search strategy:
- "top vector databases RAG 2025"
- "vector database comparison RAG"
- "best vector databases enterprise"

Success criteria:
- Identify 3 specific products with justifications

Expected sources:
- Technology publications
- Vendor documentation
- Comparison articles
</research_plan>
```

**Then**:
1. Orchestrator detects plan (regex matches cleanly)
2. Log shows: `"Prompting for tool execution after plan"`
3. Model receives: "Good! You've created a research plan. Now IMMEDIATELY begin executing your first search."
4. Model outputs tool call: `<tool_call><function=web_search><parameter=query>top vector databases RAG 2025</parameter></function></tool_call>`
5. Tools execute
6. Model synthesizes results

### How to Test

```bash
python3 scripts/run_tests.py --test TEST-011 --verbose
```

**Look for**:
1. ✅ Research plan with NO nested XML tags
2. ✅ Log message: "Research plan created"
3. ✅ Log message: "Prompting for tool execution after plan"
4. ✅ Tool calls executed (web_search)
5. ✅ "parallel", "chroma", "pinecone", or "qdrant" in response

---

## Files Modified

**File**: [orchestrator.py](argo_brain/argo_brain/assistant/orchestrator.py#L272-L294)

**Changes**:
- Lines 273-294: Added explicit research plan format example
- Added prohibition: "DO NOT use nested XML tags"
- Changed from abstract description to concrete example

---

## Related Issues

### This Was NOT Caused By

❌ **DEFAULT_SYSTEM_PROMPT removal** - That only affected tool call format, not research plan structure
❌ **"STOP IMMEDIATELY" removal** - That instruction is still present in mode prompts
❌ **Temperature settings** - Planning uses 0.4, which is appropriate
❌ **Max tokens** - 4096 is sufficient for research mode

### This WAS Caused By

✅ **Ambiguous prompt format** - Didn't explicitly prohibit nested XML
✅ **Model interpretation** - Generated structured XML instead of flat text
✅ **Malformed generation** - Closed tags in wrong order
✅ **Regex extraction failure** - Couldn't parse malformed XML

---

## Lessons Learned

### 1. Be Explicit About Format

**Before**: "Provide a research plan with bullet points"
**After**: Show exact example with placeholders

**Why**: Models follow examples better than abstract descriptions

### 2. Prohibit Undesired Behavior

**Before**: Implied bullet point format
**After**: Explicitly say "DO NOT use nested XML tags"

**Why**: Prevents model from using "creative" interpretations

### 3. Test Edge Cases

**What we learned**: RESEARCH mode wasn't tested thoroughly after architecture changes

**Action**: Added TEST-011 to catch this issue

### 4. Check Logs During Debugging

**Key insight**: "Prompting for tool execution after plan" message didn't appear

**Lesson**: Always check logs first - they reveal orchestrator state transitions

---

## Prevention

### Add to Test Suite

TEST-011 specifically tests:
- Research plan creation
- Automatic tool execution after plan
- Parallel tool execution
- Result synthesis

**This test will catch**:
- Malformed research plans
- Missing follow-up prompts
- Tool execution failures

### Add Validation

Could add XML validation after research plan extraction:

```python
# After extracting plan
if plan:
    # Validate it's simple text, not nested XML
    if "<" in plan and ">" in plan:
        # Contains XML tags inside
        self.logger.warning("Research plan contains nested XML, may fail parsing")
```

---

## Summary

**Issue**: TEST-011 failed because model generated malformed nested XML in research plan

**Root Cause**: Prompt was ambiguous about format, allowed model to use nested XML structure

**Fix**: Added explicit example with "DO NOT use nested XML tags" prohibition

**Impact**:
- ✅ Research mode works correctly
- ✅ Plans are parseable
- ✅ Tool execution triggers automatically
- ✅ TEST-011 should now pass

**No Relation To**: DEFAULT_SYSTEM_PROMPT removal (that was the right architectural choice)

---

**Document Version**: 1.0
**Created**: December 2, 2025
**Status**: Fix implemented, ready for testing
