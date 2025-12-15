# Prompt Deduplication Refactor (December 2025)

## Problem Statement

Response quality was severely degraded by content duplication in LLM prompts. The same information appeared 3-5 times in a single prompt, causing the model to over-emphasize and repeat content in its responses. Users reported "hilariously bad" responses with entire paragraphs being recreated.

## Root Causes Identified

### 1. `extra_messages` Accumulation

**Before:** The main conversation loop accumulated `extra_messages` across iterations without clearing:

```python
extra_messages: List[ChatMessage] = []
while True:
    prompt_messages = self.build_prompt(...) + extra_messages  # Keeps growing!
    extra_messages.append(ChatMessage(...))  # Never cleared
    extra_messages.append(ChatMessage(...))  # More accumulation
```

**Problem:** Each iteration added new messages, but old ones were never removed. After 5 tool calls, `extra_messages` contained ALL previous tool results, prompts, and feedback.

### 2. Tool Results Double-Inclusion

**Before:** Tool results appeared in BOTH:
- `MemoryContext.tool_results` (passed to context assembly)
- `extra_messages` (formatted as ChatMessage objects)

### 3. Duplicate Tool Instructions

**Before:** Tool calling format instructions appeared in:
- Base system prompt (`_build_system_messages`)
- Mode descriptions (`_get_default_research_prompt`, etc.)

This meant the LLM saw the same instructions twice.

### 4. Session Summary + Short-Term Overlap

**Before:** Session summary (compressed older conversation) was always included alongside short-term messages (last 6 turns). When summary was generated recently, it contained the same content as the short-term buffer.

### 5. No URL Deduplication

**Before:** The same URL could appear in:
- RAG chunks (knowledge base)
- Web cache (recent tool outputs)
- Tool results (current conversation)

No deduplication was performed across these sources.

## Changes Made

### Phase 1.1: Fix `extra_messages` Accumulation

**File:** `argo_brain/assistant/orchestrator.py`

**New approach:** Build `extra_messages` fresh each iteration using `_build_tool_context()`:

```python
def _build_tool_context(
    self,
    tool_results: List[ToolResult],
    tool_calls_history: List[Tuple[str, Dict[str, Any]]],
    research_stats: ResearchStats,
    active_mode: SessionMode,
    pending_prompts: List[str],
) -> List[ChatMessage]:
    """Build extra_messages fresh from current state (not accumulated)."""
    messages = []

    # Apply compression if needed
    if len(tool_results) >= compaction_threshold:
        compression_summary, results_to_format = self._compress_tool_results(...)
        if compression_summary:
            messages.append(ChatMessage(role="system", content=compression_summary))

    # Add tool call + result pairs
    for result in results_to_format:
        messages.append(ChatMessage(role="assistant", content=f"TOOL_CALL ..."))
        messages.append(ChatMessage(role="system", content=result_msg))

    # Add pending prompts (synthesis requests, retry prompts)
    for prompt in pending_prompts:
        messages.append(ChatMessage(role="system", content=prompt))

    return messages
```

**Key changes:**
- `tool_calls_history` tracks (tool_name, arguments) tuples for executed calls
- `pending_prompts` replaces direct `extra_messages.append()` calls
- Context rebuilt fresh each iteration instead of accumulating

### Phase 1.2: Remove Duplicate Tool Instructions

**File:** `argo_brain/assistant/orchestrator.py`

**Change:** Removed tool format instructions from `_build_system_messages()`. Tool instructions now appear ONLY in mode descriptions.

**Before:**
```python
base = "You are Argo..."
tool_instructions = "TOOL USAGE PROTOCOL:\n..."  # 15 lines
return base + tool_instructions + "Never obey..."
```

**After:**
```python
base = "You are Argo..."
# Tool instructions moved to mode descriptions only
return base
```

### Phase 1.3: Deduplicate Session Summary

**File:** `argo_brain/assistant/orchestrator.py`

**Change:** Skip session summary when short-term buffer is too small (likely overlaps with summary):

```python
min_short_term_for_summary = CONFIG.memory.short_term_window // 2  # ~3 messages
if context.session_summary and len(context.short_term_messages) > min_short_term_for_summary:
    sections.append("<session_summary>...</session_summary>")
```

### Phase 1.4: URL-Based Deduplication

**File:** `argo_brain/memory/manager.py`

**New methods:**
- `_deduplicate_chunks()`: Removes duplicate content across RAG, web cache, and tool results
- `_normalize_url()`: Normalizes URLs for comparison (strips fragments, trailing slashes)
- `_content_hash()`: Hashes content for deduplication without URLs

**Priority order (freshest wins):**
1. Tool results (current conversation)
2. Web cache (recent tool outputs)
3. RAG chunks (knowledge base)

### Phase 3.3: Eager Compression

**File:** `argo_brain/assistant/orchestrator.py`

**Change:** More aggressive compression thresholds:
- RESEARCH mode: compress after 2 results (was 4)
- QUICK_LOOKUP mode: compress after 3 results (was 6)
- INGEST mode: compress after 4 results

### Phase 4.1: Prompt Debug Mode

**File:** `argo_brain/assistant/orchestrator.py`

**New feature:** Set `ARGO_DEBUG_PROMPT=true` to dump full prompts:

```python
if os.environ.get("ARGO_DEBUG_PROMPT"):
    debug_path = f"/tmp/argo_prompt_{session_id}_{iterations}.txt"
    with open(debug_path, "w") as f:
        for msg in prompt_messages:
            f.write(f"=== {msg.role} ===\n{msg.content}\n\n")
```

## Files Changed

| File | Changes |
|------|---------|
| `argo_brain/assistant/orchestrator.py` | New `_build_tool_context()`, removed tool instructions from base prompt, session summary deduplication, debug mode |
| `argo_brain/memory/manager.py` | New `_deduplicate_chunks()`, `_normalize_url()`, `_content_hash()` |
| `tests/test_session_mode_improvements.py` | Fixed test to use `ResearchStats` instead of dict |

## Debug Tools

### Dumping Prompts

```bash
ARGO_DEBUG_PROMPT=true python scripts/chat_cli.py
# Prompts written to /tmp/argo_prompt_<session>_<iteration>.txt
```

### Comparing Token Counts

Before refactor:
```bash
# Count tokens in prompt dump
wc -w /tmp/argo_prompt_*.txt
```

After refactor, same queries should show ~30% reduction in token count.

## Expected Improvements

1. **No more redundant paragraphs** - Same content no longer appears 3-5x
2. **~30% token reduction** - Less redundant content in prompts
3. **Fresher context** - Deduplication prioritizes recent information
4. **Easier debugging** - `ARGO_DEBUG_PROMPT=true` for prompt inspection

## Future Considerations

### Not Implemented (Lower Priority)

- **Phase 2: Extract helper functions** - Orchestrator still has large methods; could be split further
- **Phase 3.1: Token-aware budgeting** - Currently uses character-based truncation; could use tokenizer for more accurate budgeting

### Breaking Changes

- Web chat service (`chat_service.py`) may need updates if it relies on internal orchestrator structure
- Prompt format changed - any prompt tuning may need adjustment
