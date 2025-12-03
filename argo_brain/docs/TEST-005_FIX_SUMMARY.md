# TEST-005 Fix Summary

**Date**: December 3, 2025
**Issue**: Research mode synthesis not triggering
**Status**: ✅ FIXED

---

## The Problem

TEST-005 and other research tests were executing tools but not generating synthesis:
- Research plan created ✓
- Tools executed ✓
- URLs tracked ❌ (only 1 of 6-8)
- Synthesis triggered ❌ (requires 3+ URLs)

---

## Root Cause

**Two code paths for tool execution, but only one tracked research stats:**

### Path 1: Batch Tool Execution (Lines 1157-1217)
```python
plan_payload = self._maybe_parse_plan(response_text)
if plan_payload:
    proposals = plan_payload["proposals"]
    approved, rejections = self.tool_policy.review(proposals, self.tool_registry)

    # Execute tools
    results = self._execute_single_tool(approved[0], ...)

    # Process results
    for proposal, result in zip(approved, results):
        # Track research progress ✓
        if proposal.tool == "web_access" and result.metadata:
            url = result.metadata.get("url")
            if url:
                research_stats["unique_urls"].add(url)  # ✓ Tracked
```

**This path tracks URLs correctly.**

### Path 2: Individual Tool Call Execution (Lines 1275-1309)
```python
tool_call = self._maybe_parse_tool_call(response_text)
if tool_call:
    result = self.run_tool(tool_name, ...)
    tool_results_accum.append(result)
    # ❌ NO research stats tracking!
    continue
```

**This path did NOT track URLs - THIS WAS THE BUG!**

---

## Why This Happened

Different LLM response formats trigger different parsing:

1. **Multiple tools in one response** → `_maybe_parse_plan()` → Path 1 (tracked)
2. **Single tool per response** → `_maybe_parse_tool_call()` → Path 2 (NOT tracked)

TEST-005 was outputting tools one at a time, so most tools went through Path 2 without URL tracking.

---

## The Fix

**File**: `orchestrator.py:1297-1317`

Added identical research stats tracking to Path 2:

```python
result = self.run_tool(tool_name, ...)
tool_results_accum.append(result)

# NEW: Track research progress (same as batch execution path)
if active_mode == SessionMode.RESEARCH:
    research_stats["tool_calls"] += 1
    if tool_name == "web_search":
        research_stats["searches"] += 1
        query = arguments.get("query", user_message)
        research_stats["search_queries"].append(str(query))
    elif tool_name == "web_access":
        if result.metadata:
            url = result.metadata.get("url")
            if url:
                research_stats["unique_urls"].add(url)  # ✓ Now tracked!
                research_stats["sources_fetched"] += 1
```

---

## Test Results

### Before Fix
```
TEST-004: 31 lines, no synthesis ❌
TEST-005: 29 lines, no synthesis ❌
TEST-011: 42 lines, synthesis ✓ (worked by chance)
```

### After Fix
```
TEST-004: 74 lines, synthesis ✓
TEST-005: 50 lines, synthesis ✓
TEST-011: 48 lines, synthesis ✓
```

All research tests now complete the full workflow:
```
Plan → Tools → URL Tracking → Synthesis Trigger → Final Answer
```

---

## Log Evidence

### Before Fix (only 1 URL tracked):
```
2025-12-03T12:28:02 Tool execution completed [web_access]
2025-12-03T12:28:02 Processing tool result [web_access]
2025-12-03T12:28:02 Added URL [...], total=1

2025-12-03T12:28:03 Tool execution completed [web_access]  ← Not processed
2025-12-03T12:28:04 Tool execution completed [web_access]  ← Not processed
2025-12-03T12:28:05 Tool execution completed [web_access]  ← Not processed
...

2025-12-03T12:28:07 Checking synthesis trigger conditions
2025-12-03T12:28:07 RESEARCH mode exiting (sources_count=1 < 3)
```

### After Fix (multiple URLs tracked):
```
2025-12-03T12:37:05 Added URL via individual tool call - url=..., total=2
2025-12-03T12:37:05 Added URL via individual tool call - url=..., total=3  ← Threshold met!
2025-12-03T12:37:06 Added URL via individual tool call - url=..., total=4

2025-12-03T12:37:07 Triggering synthesis phase after tool execution
```

---

## Additional Improvements

### 1. Test Output Enhancement

**File**: `scripts/run_tests.py:255-280`

Modified test runner to always show debug file paths:

**Before**:
```
[Only showed path in --verbose mode]
```

**After**:
```
[Response: 1234 chars, plan=✓, synthesis=✓]
[Full response saved to: /tmp/test_test-005_response.txt]
```

Benefits:
- Easy access to full test outputs
- Quick visual check of completeness (plan/synthesis flags)
- Works in both verbose and non-verbose modes

---

## Files Modified

| File | Lines | Change |
|------|-------|--------|
| `orchestrator.py` | 1297-1317 | Added research stats tracking to individual tool call path |
| `run_tests.py` | 255-280 | Always save and show debug file paths |
| `docs/TEST-005_BUG_ANALYSIS.md` | — | Comprehensive bug analysis (new) |
| `docs/TEST-005_FIX_SUMMARY.md` | — | This file (new) |

---

## Debug Logging (Removed)

Debug logging was temporarily added during troubleshooting and has been removed after verification:
- ~~Line 1192-1197: Tool result processing~~
- ~~Line 1203-1217: URL tracking (batch path)~~
- ~~Line 1310-1317: URL tracking (individual path)~~
- ~~Line 1181-1186: Result processing iteration counts~~
- ~~Line 1591-1595: Parallel execution calls~~
- ~~Line 1633-1638: Parallel execution returns~~

**Status**: ✅ All debug logging removed after successful verification.

---

## Why URL Tracking is Critical

Research mode synthesis requires 3+ unique URLs:

```python
# orchestrator.py:1336-1351
if active_mode == SessionMode.RESEARCH:
    has_plan = research_stats.get("has_plan", False)
    sources_count = len(research_stats.get("unique_urls", set()))

    if has_plan and sources_count >= 3:  # ← Threshold check
        # Trigger synthesis
```

Without proper URL tracking from all tool execution paths:
1. `sources_count` stays low (was 1 for TEST-005)
2. Synthesis never triggers
3. Loop exits with only research plan
4. Test "passes" but output incomplete

---

## Lessons Learned

### 1. Multiple Code Paths = Multiple Tracking Points
When adding state tracking (like research stats), audit ALL code paths that affect that state.

### 2. Comprehensive Logging is Essential
Debug logging at both code paths immediately revealed the issue:
- "Added URL" only appeared 1-2 times
- "Tool execution completed" appeared 10 times
- Gap = bug location

### 3. Test Validation vs Behavior
Tests were "passing" (11/11) but behavior was broken. Validation relaxed to reduce false failures, but masked real issues.

**Recommendation**: Add stricter validation for research mode:
- Require `<synthesis>` tag for RESEARCH tests
- Require minimum output length (>40 lines)
- Check for `<confidence>` and `<gaps>` tags

---

## Future Improvements

### 1. Refactor Duplicate Code
Lines 1199-1217 and 1297-1317 have identical research stats tracking logic.

**Recommendation**: Extract to helper method:
```python
def _track_research_tool_result(
    self,
    research_stats: Dict,
    tool_name: str,
    arguments: Dict,
    result: ToolResult,
    user_message: str,
    session_id: str
) -> None:
    """Track research progress for any tool execution path."""
    research_stats["tool_calls"] += 1
    if tool_name == "web_search":
        # ... track search ...
    elif tool_name == "web_access":
        # ... track URL ...
```

### 2. Add Integration Test
Test that specifically validates URL tracking:
```python
def test_url_tracking_both_paths():
    """Verify URLs tracked regardless of execution path."""
    # Test batch execution
    # Test individual execution
    # Assert same behavior
```

### 3. Monitor Path Usage
Add metrics to track which execution path is used:
```python
research_stats["batch_executions"] = 0
research_stats["individual_executions"] = 0
```

This would have immediately shown the imbalance (2 batch vs 8 individual).

---

## Verification

To verify the fix works correctly:

```bash
# Run all research tests
python scripts/run_tests.py --test TEST-004 --auto
python scripts/run_tests.py --test TEST-005 --auto
python scripts/run_tests.py --test TEST-011 --auto

# Check outputs have synthesis
grep "<synthesis>" /tmp/test_test-004_response.txt
grep "<synthesis>" /tmp/test_test-005_response.txt
grep "<synthesis>" /tmp/test_test-011_response.txt

# Check logs show URL tracking
tail -500 .argo_data/state/logs/argo_brain.log | grep "Added URL via individual"
```

All should show synthesis present and multiple URLs tracked.
