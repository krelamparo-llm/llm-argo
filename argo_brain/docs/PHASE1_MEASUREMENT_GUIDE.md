# Phase 1 Measurement Guide

## Overview

This guide explains how to measure the impact of Phase 1 improvements (tool descriptions, response_format, parallel execution) using Argo's existing logging infrastructure.

---

## 📊 What Metrics Are Already Logged

### 1. **LLM Request Metrics** (llm_client.py)

**Automatically logged for every LLM call**:
```python
self.logger.info(
    "LLM request completed",
    extra={
        "status_code": response.status_code,
        "elapsed_ms": round(elapsed * 1000, 2),  # ← Time taken
        "tokens_max": payload.get("max_tokens"),   # ← Max tokens requested
    },
)
```

**Location**: `argo_brain/llm_client.py:119-126`

**What it tells us**:
- ✅ LLM call duration (milliseconds)
- ✅ Max tokens parameter
- ✅ HTTP status

**What's missing**:
- ❌ Actual tokens used (prompt + completion)
- ❌ Token count from llama-server response

---

### 2. **Tool Execution Metrics** (tool_tracker.py)

**Automatically logged for every tool execution**:
```python
self.logger.info(
    "Tool execution completed",
    extra={
        "tool_name": result.tool_name,           # ← Which tool
        "session_id": session_id,
        "input_length": len(request.query),       # ← Input size
        "output_length": len(result.content),     # ← Output size (chars)
        "has_snippets": bool(result.snippets),
        "snippet_count": len(result.snippets),
        "metadata_keys": list(result.metadata.keys()),
    }
)
```

**Location**: `argo_brain/memory/tool_tracker.py:46-57`

**What it tells us**:
- ✅ Tool name
- ✅ Input/output character counts
- ✅ Snippet availability
- ✅ Metadata fields (including response_format!)

---

### 3. **Session Metrics** (orchestrator.py)

**User message received**:
```python
self.logger.info(
    "User message received",
    extra={"session_id": session_id, "chars": len(user_message)},
)
```

**Assistant response completed**:
```python
self.logger.info(
    "Assistant completed response",
    extra={"session_id": session_id, "tool_runs": len(tool_results_accum)},
)
```

**What it tells us**:
- ✅ Message character counts
- ✅ Total tool runs per query

---

### 4. **Parallel Execution Metrics** (NEW in Phase 1)

**Parallel tool execution log** (orchestrator.py:573-576):
```python
self.logger.info(
    f"Executing {len(approved)} tools in parallel",
    extra={"session_id": session_id, "tools": [p.tool for p in approved]}
)
```

**What it tells us**:
- ✅ Number of tools executed in parallel
- ✅ Which tools ran together

---

### 5. **Response Format Metrics** (NEW in Phase 1)

**Web access metadata** (web.py:94-105):
```python
metadata: Dict[str, Any] = {
    # ... existing fields
    "response_format": response_format,      # ← NEW: "concise" or "detailed"
    "full_length": len(full_content),        # ← NEW: Original article length
    "word_count": len(full_content.split()), # ← NEW: Word count
}
```

**What it tells us**:
- ✅ Which response format was used
- ✅ Original content size vs. returned size (for concise mode)
- ✅ Token savings from concise mode

---

## 🎯 Measurement Strategy

### **Baseline Measurement (Before Phase 1)**

Since Phase 1 is already implemented, we need to compare against:
1. **Historical logs** (if you have logs from before today)
2. **Controlled tests** with `response_format="detailed"` to simulate old behavior

### **Key Metrics to Track**

| Metric | Log Source | Field | Phase 1 Impact |
|--------|-----------|-------|----------------|
| **LLM Call Duration** | llm_client | `elapsed_ms` | Should decrease (parallel tools) |
| **Tool Output Size** | tool_tracker | `output_length` | Should decrease 80% (concise mode) |
| **Total Query Time** | orchestrator | Start to completion | Should decrease 50-70% |
| **Tools Per Query** | orchestrator | `tool_runs` | Should stay same or slightly increase |
| **Parallel Executions** | orchestrator | Count of parallel logs | NEW metric |
| **Response Format Usage** | web.py metadata | `response_format` | Track concise vs detailed |
| **Token Savings** | web.py metadata | `full_length` - `output_length` | NEW metric |

---

## 📝 How to Measure

### **Method 1: Live Log Analysis** (Recommended)

Run a research query and grep the logs in real-time:

```bash
# Start argo with logging
source ~/venvs/llm-wsl/bin/activate
cd /home/krela/llm-argo/argo_brain
python -m argo_brain.cli

# In another terminal, tail logs with specific filters
tail -f ~/.argo_data/logs/argo_brain.log | grep -E "LLM request completed|Tool execution completed|Executing.*parallel|Assistant completed"
```

**Example output to watch for**:
```
2025-12-01 16:30:01 [INFO] User message received [session_id=abc123, chars=45]
2025-12-01 16:30:02 [INFO] Executing 3 tools in parallel [session_id=abc123, tools=['web_search', 'web_access', 'web_access']]
2025-12-01 16:30:05 [INFO] Tool execution completed [tool_name=web_search, output_length=1234]
2025-12-01 16:30:06 [INFO] Tool execution completed [tool_name=web_access, output_length=2156, metadata_keys=['response_format', 'full_length', 'word_count']]
2025-12-01 16:30:08 [INFO] LLM request completed [elapsed_ms=15234.5, tokens_max=4096]
2025-12-01 16:30:08 [INFO] Assistant completed response [session_id=abc123, tool_runs=7]
```

---

### **Method 2: Structured Log Parsing**

Create a Python script to parse and aggregate metrics:

```python
#!/usr/bin/env python3
"""Parse Argo logs and extract Phase 1 metrics."""

import json
import re
from pathlib import Path
from collections import defaultdict

log_file = Path.home() / "llm-argo/.argo_data/logs/argo_brain.log"

metrics = {
    "llm_calls": [],
    "tool_executions": [],
    "parallel_executions": [],
    "sessions": defaultdict(dict),
}

with open(log_file) as f:
    for line in f:
        # LLM request completed
        if "LLM request completed" in line:
            match = re.search(r"elapsed_ms=([\d.]+)", line)
            if match:
                metrics["llm_calls"].append(float(match.group(1)))

        # Tool execution with response_format
        if "Tool execution completed" in line and "web_access" in line:
            output_match = re.search(r"output_length=(\d+)", line)
            if output_match:
                metrics["tool_executions"].append(int(output_match.group(1)))

        # Parallel execution
        if "Executing" in line and "parallel" in line:
            count_match = re.search(r"Executing (\d+) tools", line)
            if count_match:
                metrics["parallel_executions"].append(int(count_match.group(1)))

# Calculate statistics
print("=== Phase 1 Metrics ===\n")

if metrics["llm_calls"]:
    avg_llm = sum(metrics["llm_calls"]) / len(metrics["llm_calls"])
    print(f"LLM Calls: {len(metrics['llm_calls'])}")
    print(f"  Avg duration: {avg_llm:.1f}ms")
    print(f"  Min: {min(metrics['llm_calls']):.1f}ms")
    print(f"  Max: {max(metrics['llm_calls']):.1f}ms")

if metrics["tool_executions"]:
    avg_output = sum(metrics["tool_executions"]) / len(metrics["tool_executions"])
    print(f"\nTool Executions: {len(metrics['tool_executions'])}")
    print(f"  Avg output size: {avg_output:.0f} chars")

if metrics["parallel_executions"]:
    total_parallel = sum(metrics["parallel_executions"])
    print(f"\nParallel Executions: {len(metrics['parallel_executions'])}")
    print(f"  Total tools run in parallel: {total_parallel}")
    print(f"  Avg tools per parallel batch: {total_parallel / len(metrics['parallel_executions']):.1f}")
```

**Save as**: `scripts/analyze_phase1_metrics.py`

**Run**:
```bash
python scripts/analyze_phase1_metrics.py
```

---

### **Method 3: Database Queries**

ToolTracker stores tool executions in SQLite:

```bash
sqlite3 ~/.argo_data/state/memory.db
```

**Useful queries**:

```sql
-- Count tool executions by type
SELECT tool_name, COUNT(*) as count
FROM tool_runs
WHERE timestamp > datetime('now', '-1 hour')
GROUP BY tool_name;

-- Average output length by tool
SELECT tool_name, AVG(LENGTH(output_ref)) as avg_length
FROM tool_runs
WHERE timestamp > datetime('now', '-1 hour')
GROUP BY tool_name;

-- Recent web_access calls (to check response_format usage)
SELECT timestamp, input_payload, LENGTH(output_ref) as output_size
FROM tool_runs
WHERE tool_name = 'web_access'
ORDER BY timestamp DESC
LIMIT 10;
```

---

## 🧪 Recommended Test Queries

### **Test 1: Baseline (Simulate Old Behavior)**

Force detailed mode to simulate pre-Phase-1 behavior:

```
Argo> research what are the latest best practices for LLM agent tool calling in 2025
```

Then manually check logs to see if model uses `response_format="detailed"` or defaults to concise.

**Expected**: Model should use "concise" by default (Phase 1 improvement)

---

### **Test 2: Parallel Execution**

Research query that should trigger multiple web_access calls:

```
Argo> research Claude tool calling best practices, compare with LangChain and Microsoft Semantic Kernel approaches
```

**Expected logs**:
```
[INFO] Executing 3 tools in parallel [tools=['web_access', 'web_access', 'web_access']]
```

**Measure**:
- Time from "Executing...parallel" to "LLM request completed"
- Should be ~3x faster than sequential (since 3 tools complete simultaneously)

---

### **Test 3: Token Savings (Concise Mode)**

Single web_access to a long article:

```
Argo> fetch and summarize https://www.anthropic.com/research/building-effective-agents
```

**Check logs for**:
```
[INFO] Tool execution completed [tool_name=web_access, output_length=2500, metadata_keys=['response_format', 'full_length', 'word_count']]
```

**Calculate savings**:
- `full_length` (original) vs `output_length` (returned)
- Should see ~80% reduction with concise mode

---

### **Test 4: Tool Selection Accuracy**

Query that should trigger memory_query first:

```
Argo> what did we research about Anthropic best practices?
```

**Expected**: Model should use `memory_query` before `web_search` (per enhanced tool descriptions)

**Measure**: Check tool execution order in logs

---

## 📈 Expected Improvements

Based on Anthropic research and our implementations:

| Metric | Baseline (Estimated) | Phase 1 Target | Measurement |
|--------|---------------------|----------------|-------------|
| **LLM call duration** | 30-60s | 30-60s (similar) | `elapsed_ms` in logs |
| **Tool output size** (web_access) | 10,000 chars | 2,000 chars (80% ↓) | `output_length` in logs |
| **Total research time** (3 tools) | 120s (3×40s) | 50s (parallel) | Start to completion |
| **Parallel execution rate** | 0% | >50% of multi-tool queries | Count parallel logs |
| **Tool selection accuracy** | Baseline | +10-25% | Manual review |
| **Context size** | 4,330 tokens | 2,000-2,500 tokens | Manual prompt inspection |

---

## 🔍 Quick Measurement Checklist

**Before Phase 2, measure these**:

- [ ] Run 3 research queries with different topics
- [ ] Check logs for parallel execution count
- [ ] Verify web_access uses `response_format="concise"` by default
- [ ] Calculate avg tool output size (should be ~2K chars for web_access)
- [ ] Measure total query time (user message → assistant response)
- [ ] Confirm synthesis appears after tool execution
- [ ] Check if model follows enhanced tool descriptions (memory_query before web_search when applicable)

---

## 💡 Tips for Accurate Measurement

1. **Clear logs before testing**:
   ```bash
   > ~/.argo_data/logs/argo_brain.log  # Clear log file
   ```

2. **Use same queries** for baseline vs. optimized comparisons

3. **Run multiple iterations** (3-5) to get averages

4. **Note the session_id** for each test to filter logs:
   ```bash
   grep "session_id=abc123" argo_brain.log
   ```

5. **Check metadata** in tool execution logs for response_format and token savings

6. **Time end-to-end** using:
   ```bash
   time echo "research query here" | python -m argo_brain.cli
   ```

---

## 🚀 Next Steps After Measurement

Once you have baseline metrics:

1. **Compare against Phase 1 targets** (see Expected Improvements table)
2. **Identify bottlenecks** still present
3. **Validate** if Phase 2 (context optimization) is needed
4. **Document findings** for Phase 2 planning

---

## 📚 Log Locations

- **Application logs**: `~/.argo_data/logs/argo_brain.log`
- **Database**: `~/.argo_data/state/memory.db`
- **Session state**: `~/.argo_data/state/sessions.json`

---

## ❓ FAQ

**Q: Can I get token counts from llama-server?**

A: Yes, but it requires parsing the response JSON. llama-server returns:
```json
{
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801
  }
}
```

**Enhancement needed**: Modify `llm_client.py` to extract and log these:

```python
# In llm_client.py:chat() after line 131
data = response.json()
usage = data.get("usage", {})
self.logger.info(
    "LLM token usage",
    extra={
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
)
```

**Q: How do I measure "context rot" prevention?**

A: Context rot is qualitative. Test by:
1. Running long research sessions (15+ tool calls)
2. Checking if synthesis quality degrades
3. Monitoring if model misses information from early tool results
4. Phase 2 (context optimization) will help prevent this

**Q: Can I compare before/after Phase 1?**

A: If you have historical logs from before today, yes! Use the log parsing script to compare. Otherwise, test with `response_format="detailed"` to simulate old behavior.

---

## Summary

✅ **What's already measurable**:
- LLM call duration
- Tool output sizes
- Parallel execution counts
- Response format usage
- Character/word counts

❌ **What requires enhancements**:
- Token counts from llama-server (needs code change)
- Context window usage (needs manual inspection)
- Tool selection accuracy (needs manual review)

**Best approach**: Use Method 1 (Live Log Analysis) for quick validation, then Method 2 (Structured Parsing) for detailed analysis.
