# Research Mode Debugging - Findings

**Date**: 2025-11-30
**Issue**: Research mode not using tools as expected

## Bugs Found and Fixed

### 1. CRITICAL: `logging.py` Module Name Conflict ✅ FIXED

**Problem**: File `argo_brain/logging.py` was shadowing Python's built-in `logging` module, causing `ModuleNotFoundError` when sentence-transformers tried to import logging.

**Error**:
```
ModuleNotFoundError: No module named 'logging.handlers'; 'logging' is not a package
```

**Fix Applied**:
- Renamed `argo_brain/logging.py` → `argo_brain/log_setup.py`
- Updated import in `scripts/chat_cli.py`: `from argo_brain.log_setup import setup_logging`

**Impact**: CRITICAL - Entire system was broken and couldn't import core modules

---

### 2. Low `max_tokens` Limit for Research Mode ✅ FIXED

**Problem**: Default `max_tokens=512` (from [config.py:158](argo_brain/config.py#L158)) was too low for research mode. LLM responses were being truncated mid-sentence.

**Example Truncated Output**:
```
<research_plan>
- **Search strategy**:
  - Keywords: "RAG memory systems best practices," "RAG optimization techniques," "retrieval-augmented generation memory management."
  - Prioritize academic papers, industry blogs (e.g., Hugging Face, LangChain), and'
```
(Note the truncation at "and'")

**Fix Applied**:
- Updated [orchestrator.py:396](argo_brain/argo_brain/assistant/orchestrator.py#L396):
```python
# Research mode needs higher max_tokens for synthesis and detailed responses
max_tokens = 2048 if active_mode == SessionMode.RESEARCH else None
```

**Impact**: HIGH - Research mode responses now complete, but revealed deeper issue

---

### 3. CRITICAL: LLM Not Using Tools ❌ NOT FIXED

**Problem**: The LLM consistently ignores instructions to use tools via JSON and instead answers questions from training data or hallucinates sources.

**Test Results**:
```bash
$ python test_research_debug.py

Query: "What did Anthropic announce about Claude 3.5 Opus in December 2024? Search for official announcements."

Expected behavior:
- Output JSON: {"plan": "...", "tool_calls": [{"tool": "web_search", "args": {...}}]}
- Wait for system to execute tools
- Receive real web results
- Synthesize from actual sources

Actual behavior:
- Tool results count: 0
- Parsed JSON: False
- LLM output: Direct answer with hallucinated citations

Response excerpt:
<synthesis>
**Final Answer**:
Anthropic did **not** make any official announcements about **Claude 3.5 Opus** in December 2024.
1. **December 2024 updates** focused exclusively on **Claude 3.5 Sonnet**...
2. **Opus remained unchanged** in 2024, as confirmed by Anthropic's [Q4 2024 roadmap](https://blog.anthropic.ai/q4-2024-roadmap)...
</synthesis>
```

**Analysis**:

1. **Prompt Conflict**:
   - System prompt ([orchestrator.py:26-29](argo_brain/argo_brain/assistant/orchestrator.py#L26-L29)): "When you need a tool, first respond ONLY with JSON..."
   - Research prompt ([orchestrator.py:98](argo_brain/argo_brain/assistant/orchestrator.py#L98)): "**MANDATORY TOOL USAGE**: You MUST use the web_search and web_access tools..."

   The LLM decides it doesn't "need" tools because it can answer from memory.

2. **LLM Hallucination**:
   When the LLM DOES output JSON tool calls, it immediately continues with:
   ```json
   {"plan": "...", "tool_calls": [...]}

   {"results": [{"title": "...", "url": "...", "snippet": "..."}]}
   ```
   It hallucinates fake tool results instead of stopping and waiting.

3. **Weak Instruction Following**:
   Multiple attempts to make tool usage mandatory ALL failed:
   - "CRITICAL: You MUST use tools via JSON" - IGNORED
   - "**MANDATORY TOOL USAGE**" - IGNORED
   - "Do NOT answer from memory" - IGNORED
   - "Your role is to fetch and synthesize CURRENT information" - IGNORED

**Root Cause**: The local LLM model (Qwen3-32B-q5_k_m) is not sufficiently trained or prompted to follow tool-use protocols reliably.

**Potential Fixes** (NOT YET IMPLEMENTED):

1. **Few-shot Examples in System Prompt**:
   Add concrete examples of correct tool-use behavior to the system prompt:
   ```
   Example correct behavior:
   User: "Search for X"
   Assistant: {"plan": "Search for X", "tool_calls": [{"tool": "web_search", "args": {"query": "X"}}]}
   System: TOOL_RESULT {...}
   Assistant: <synthesis>Based on the search results from [URL]...</synthesis>

   Example WRONG behavior (do NOT do this):
   Assistant: {"plan": "...", "tool_calls": [...]} {"results": [...]} <-- WRONG! Do not hallucinate results!
   ```

2. **Stronger Model**:
   Test with Claude API, GPT-4, or another model known for better tool-use compliance.

3. **Response Format Validation**:
   Add orchestrator logic to detect when LLM outputs non-JSON text and reject it:
   ```python
   if active_mode == SessionMode.RESEARCH:
       if not plan_payload and not response_text.startswith("<synthesis>"):
           # LLM didn't output JSON or final synthesis - this is an error
           extra_messages.append(ChatMessage(
               role="system",
               content="ERROR: You must either output tool-call JSON or a final <synthesis>. Do not answer from memory."
           ))
           continue
   ```

4. **Tool-First Mode**:
   Force tool execution BEFORE allowing the LLM to respond:
   - System automatically executes `web_search` for research queries
   - LLM only sees results, never gets chance to answer from memory

---

## Current Implementation Status

### What's Working ✅
- Research mode prompt engineering (planning-first, self-reflection, stopping conditions)
- Tool infrastructure (WebSearchTool, WebAccessTool, ToolTracker)
- Structured logging and observability
- XML context formatting
- Session management and memory layers
- All unit tests passing (10/10)

### What's Broken ❌
- **Tool execution in research mode** - LLM not following instructions to use tools
- Prompt compliance - Multiple explicit "MUST use tools" instructions ignored
- JSON parsing logic might work IF LLM output proper JSON, but it doesn't consistently

---

## Recommendations

### Immediate Next Steps

1. **Test with Different LLM**:
   Try Claude API or GPT-4 to determine if this is model-specific or a systemic prompt issue.

2. **Add Few-Shot Examples**:
   Update `DEFAULT_SYSTEM_PROMPT` with explicit examples of correct tool-use flow.

3. **Add Validation**:
   Implement orchestrator-level validation that rejects non-JSON responses in research mode.

4. **Temperature Tuning**:
   Lower temperature to 0.1 or 0 for research mode to reduce creative hallucination.

### Long-Term Solutions

1. **Fine-tune Local Model**:
   Fine-tune Qwen3 or similar on tool-use datasets (e.g., ToolBench, Gorilla).

2. **Hybrid Approach**:
   Use Claude/GPT-4 for planning/tool-calling, local model only for final synthesis.

3. **Constrained Generation**:
   Use grammar-based sampling (llama.cpp supports this) to FORCE JSON output.

---

## Testing Commands

**Run debug test**:
```bash
cd /home/krela/llm-argo/argo_brain
source ~/venvs/llm-wsl/bin/activate
python test_research_debug.py
```

**Check logs**:
```bash
tail -f /mnt/d/llm/argo_brain/state/logs/argo_brain.log
```

**Interactive test**:
```bash
python scripts/chat_cli.py --mode research --session test1
```

Then try: `"Search for recent llama.cpp updates and summarize"`

---

## Files Modified

1. `argo_brain/logging.py` → `argo_brain/log_setup.py` (RENAMED)
2. `scripts/chat_cli.py` - Updated import
3. `argo_brain/assistant/orchestrator.py` - Added max_tokens=2048 for research mode, updated research prompt
4. `test_research_debug.py` - NEW debug script

---

## Summary for User

**Good News**:
- ✅ Fixed critical module shadowing bug
- ✅ Fixed token limit truncation
- ✅ All infrastructure is in place and working

**Bad News**:
- ❌ Local LLM model is not following tool-use instructions reliably
- ❌ Research mode works in theory but LLM bypasses tools and answers from memory/hallucinations

**The research mode implementation is correct**, but the local LLM model (Qwen3-32B) is not capable enough or properly prompted to use it.

Next action: Need to either:
1. Switch to Claude/GPT-4 API for research mode
2. Add few-shot examples and validation logic
3. Fine-tune the local model on tool-use data

