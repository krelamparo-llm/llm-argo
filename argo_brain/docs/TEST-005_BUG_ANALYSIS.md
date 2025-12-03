# TEST-005 Bug Analysis: Incomplete Tool Result Processing

**Date**: December 3, 2025
**Issue**: TEST-005 executes tools but doesn't synthesize results
**Status**: Root cause identified, fix pending

---

## Problem Summary

TEST-005 passes validation but produces incomplete output:
- ✅ Research plan created
- ✅ 10 tools executed (3-4 web_search + 6-7 web_access)
- ❌ **Only 1 unique URL tracked** (need 3+ for synthesis)
- ❌ **No synthesis generated**
- ❌ Output contains only research plan (30 lines vs 88+ lines for working tests)

---

## Root Cause

**Tools execute but their results are not processed for URL tracking.**

### Evidence from Logs

Session `test_test-005_1764793834`:

```
2025-12-03T12:30:41 Tool execution completed [web_search]
2025-12-03T12:30:41 About to process 1 results
2025-12-03T12:30:41 Processing tool result [web_search]  ← Processed ✓

2025-12-03T12:30:43 Tool execution completed [web_search]
2025-12-03T12:30:43 About to process 1 results
2025-12-03T12:30:43 Processing tool result [web_search]  ← Processed ✓

2025-12-03T12:30:44 Tool execution completed [web_search]
2025-12-03T12:30:45 Tool execution completed [web_access]  ← Executed but NOT processed
2025-12-03T12:30:45 Tool execution completed [web_access]  ← Executed but NOT processed
2025-12-03T12:30:46 Tool execution completed [web_access]  ← Executed but NOT processed
2025-12-03T12:30:48 Tool execution completed [web_search]
2025-12-03T12:30:49 Tool execution completed [web_access]  ← Executed but NOT processed
2025-12-03T12:30:50 Tool execution completed [web_access]  ← Executed but NOT processed
2025-12-03T12:30:51 Tool execution completed [web_access]  ← Executed but NOT processed

[No "Processing tool result" messages for these 8 tools]

2025-12-03T12:30:53 Checking synthesis trigger conditions
2025-12-03T12:30:53 RESEARCH mode exiting without tool call
```

**Result**: Only 2 of 10 tool results were processed, only 1 URL tracked, synthesis never triggered.

---

## Technical Analysis

### The Execution vs Processing Gap

**File**: `orchestrator.py:1180-1197`

```python
# Process results
for proposal, result in zip(approved, results):
    if iterations >= max_tool_calls:  # Line 1189
        break
    iterations += 1

    tool_results_accum.append(result)

    # Track research progress
    research_stats["tool_calls"] += 1
    if proposal.tool == "web_search":
        # ... track search ...
    elif proposal.tool == "web_access":
        # ... track URL ...  ← This code doesn't run for 8 tools!
        if result.metadata:
            url = result.metadata.get("url")
            if url:
                research_stats["unique_urls"].add(url)  # Only happens 1-2 times
```

### Why Tools Execute But Aren't Processed

**Hypothesis**: The LLM is outputting tool calls one at a time in separate responses, but somewhere between tool execution and result processing, results are being lost or not associated with their proposals.

#### Key Observations:

1. **Tools execute one at a time**: `len(approved) == 1` always (no parallel execution)
   - Log shows: "About to process 1 results" repeatedly
   - Never shows: "Executing X tools in parallel"

2. **Tool execution completes**: ToolTracker logs "Tool execution completed" for all 10 tools

3. **Result processing stops early**: Only first 2 "Processing tool result" messages

4. **Loop exits prematurely**: After processing 2 results, loop checks synthesis conditions and exits

### Possible Causes

#### Theory 1: LLM stops outputting tool calls early
- LLM outputs 2 tool calls, then stops
- Remaining 8 tools somehow execute via different code path (retry? background?)
- **Evidence**: Only 2 "Processing tool result" messages

#### Theory 2: Result/Proposal Mismatch
- Tools execute but `zip(approved, results)` doesn't align
- Some results have no matching proposal
- **Evidence**: 10 executions but only 2 processings

#### Theory 3: Loop Exit Logic Issue
- Loop exits before processing all accumulated tool results
- **Evidence**: "RESEARCH mode exiting" happens while 8 tools are still running/just completed

---

## Comparison: Working vs Broken Tests

### TEST-004 (WORKS) - 88 lines output
```
Plan → 3 web_search → 3 web_access (3 unique URLs tracked) → Synthesis ✓
```

### TEST-011 (WORKS) - 42 lines output
```
Plan → 3 web_search → 3 web_access (3 unique URLs tracked) → Synthesis ✓
```

### TEST-005 (BROKEN) - 30 lines output
```
Plan → 2 web_search processed → [8 more tools execute but not processed] → Only 1 URL → No synthesis ✗
```

---

## Synthesis Trigger Logic

**File**: `orchestrator.py:1284-1301`

```python
if active_mode == SessionMode.RESEARCH and not research_stats.get("synthesis_triggered"):
    has_plan = research_stats.get("has_plan", False)
    sources_count = len(research_stats.get("unique_urls", set()))

    if has_plan and sources_count >= 3:  # ← TEST-005 has sources_count=1
        research_stats["synthesis_triggered"] = True
        # ... trigger synthesis ...
```

**TEST-005 state at synthesis check**:
- `has_plan`: True ✓
- `sources_count`: 1 ❌ (need 3+)
- **Result**: Synthesis doesn't trigger, loop exits

---

## URL Tracking Logic

**File**: `orchestrator.py:1203-1217`

```python
elif proposal.tool == "web_access":
    if result.metadata:
        url = result.metadata.get("url")
        if url:
            research_stats["unique_urls"].add(url)
            research_stats["sources_fetched"] += 1
```

**Debug logs show**:
- Only 1 "Added URL to research tracking" message
- Same URL added twice in different test runs
- No "NO metadata" warnings (code block not reached for other tools)

---

## Critical Questions

1. **Where are the 8 unprocessed tools coming from?**
   - They complete (ToolTracker logs them)
   - But orchestrator never processes their results
   - Are they from a previous iteration? Background retry?

2. **Why does the loop exit after processing only 2 results?**
   - max_tool_calls = 10
   - iterations after 2 tools = 2
   - Should continue to process more tools
   - But loop exits checking synthesis conditions

3. **Is there a timing issue?**
   - Tools execute asynchronously
   - Results logged after loop exits?
   - But ToolTracker logs show executions happen DURING the session, not after

---

## Recommended Fix Strategy

### Option 1: Ensure All Executed Tools Are Processed
- Track tool executions separately from proposals
- Process all tool results even if proposals don't match
- **Risk**: May process duplicate or orphaned results

### Option 2: Wait for All Tools Before Synthesis Check
- Don't check synthesis until no tools are executing
- Add state tracking: "tools_in_flight"
- **Risk**: Harder to implement, requires async coordination

### Option 3: Fix Root Cause (Recommended)
- Investigate WHY tools execute but aren't proposed/approved
- Find where the execution/processing disconnect happens
- Add tracing to track proposal → execution → result → processing flow
- **Best**: Fixes underlying issue rather than symptoms

---

## Next Steps

1. **Add comprehensive tracing**:
   ```python
   # At proposal time
   self.logger.info(f"TRACE: Proposals approved: {[p.tool for p in approved]}")

   # At execution time
   self.logger.info(f"TRACE: Executing tool: {proposal.tool}")

   # At result processing time
   self.logger.info(f"TRACE: Processing result: {result.tool_name}")
   ```

2. **Check for orphaned tool executions**:
   - Search codebase for other places that call `run_tool()` or `_execute_single_tool()`
   - Verify no retry logic is re-executing tools outside main loop

3. **Verify proposal/result pairing**:
   - Log lengths: `len(approved)` vs `len(results)`
   - Ensure `zip(approved, results)` never truncates

4. **Test hypothesis**:
   - Modify TEST-005 to force parallel execution
   - Check if parallel execution changes behavior
   - Verify if it's specific to sequential tool execution

---

## Temporary Workaround

Lower synthesis threshold for TEST-005 specifically:

```python
# HACK: Temporary fix for TEST-005
if sources_count >= 1 and "RAG" in user_message:  # Instead of >= 3
    trigger_synthesis()
```

**Not recommended**: Masks root cause without fixing it.

---

## Files Modified for Debugging

- `orchestrator.py:1192-1197`: Added tool processing debug logs
- `orchestrator.py:1203-1217`: Added URL tracking debug logs
- `orchestrator.py:1181-1186`: Added result processing debug logs
- `orchestrator.py:1591-1595`: Added parallel execution debug logs
- `orchestrator.py:1633-1638`: Added parallel execution return debug logs

All debug logs should be removed after fix is verified.
