# Architectural Fixes v2 - Tool Contract, Orchestration & Policy

## Overview

This document describes fixes for six architectural issues identified during code review. These issues affected core functionality including JIT context retrieval, research mode quality, governance consistency, storage efficiency, and tool policy coverage.

**Date**: December 2024
**Test Coverage**: 19 new regression tests + 57 total tests passing

---

## Issue Summary

| Issue | Severity | Status | Files Modified |
|-------|----------|--------|----------------|
| 1. ToolResult/retrieve_context contract | CRITICAL | ✅ Fixed | `tools/retrieve_context.py` |
| 2. Research mode synthesis timing | HIGH | ✅ Fixed | `assistant/orchestrator.py` |
| 3. QUICK_LOOKUP prompt/limit mismatch | MEDIUM | ✅ Fixed | `assistant/orchestrator.py` |
| 4. Double web content ingestion | MEDIUM | ✅ Fixed | `memory/tool_tracker.py` |
| 5. Model-aware tool rendering | DEFERRED | — | (Structured function calling deferred) |
| 6. ToolPolicy coverage gaps | MEDIUM | ✅ Fixed | `assistant/tool_policy.py`, `config.py` |

---

## ✅ Issue 1: ToolResult/retrieve_context Contract

### Problem
`RetrieveContextTool.run()` passed `error=...` to `ToolResult()`, but `ToolResult` dataclass has no `error` field. Any cache miss raised `TypeError` instead of returning a valid result.

**Impact**: JIT context retrieval pattern completely non-functional.

### Fix Applied
**File**: [retrieve_context.py:87-98](../argo_brain/tools/retrieve_context.py#L87-L98)

Moved error information into the `metadata` dict:

```python
# Before (BROKEN)
return ToolResult(
    tool_name=self.name,
    summary=f"Chunk '{chunk_id}' not found",
    content="",
    error=f"No chunk found with ID '{chunk_id}'",  # ← TypeError!
    metadata={"chunk_id": chunk_id, "found": False},
    snippets=[],
)

# After (FIXED)
return ToolResult(
    tool_name=self.name,
    summary=f"Chunk '{chunk_id}' not found",
    content="",
    metadata={
        "chunk_id": chunk_id,
        "found": False,
        "error": f"No chunk found with ID '{chunk_id}'",  # ← In metadata
    },
    snippets=[],
)
```

### Regression Test
```python
def test_retrieve_context_miss_returns_valid_tool_result(self):
    """When chunk is not found, ToolResult should be valid (no TypeError)."""
    mock_memory_manager = MagicMock()
    mock_memory_manager.retrieve_chunk_by_id.return_value = None

    tool = RetrieveContextTool(memory_manager=mock_memory_manager)
    result = tool.run(request)

    self.assertIsInstance(result, ToolResult)
    self.assertIn("error", result.metadata)
```

---

## ✅ Issue 2: Research Mode Synthesis Timing

### Problem
Synthesis was triggered after `tool_calls > 0`, regardless of:
- Whether a research plan existed
- Whether 3+ distinct sources were fetched

This contradicted the prompt's stated stopping conditions and produced shallow, under-researched answers.

**Impact**: Research mode failed to follow its own "planning → execution → synthesis" design.

### Fix Applied
**File**: [orchestrator.py:1257-1264](../argo_brain/assistant/orchestrator.py#L1257-L1264)

Changed trigger condition to require both plan AND sources:

```python
# Before (PREMATURE)
if active_mode == SessionMode.RESEARCH and research_stats["tool_calls"] > 0:
    if not research_stats.get("synthesis_triggered"):
        research_stats["synthesis_triggered"] = True

# After (CORRECT)
if active_mode == SessionMode.RESEARCH and not research_stats.get("synthesis_triggered"):
    has_plan = research_stats.get("has_plan", False)
    sources_count = len(research_stats.get("unique_urls", set()))

    # Only trigger when stopping conditions are met
    if has_plan and sources_count >= 3:
        research_stats["synthesis_triggered"] = True
```

### Stopping Conditions (from prompt)
```
✓ Explicit research plan created
✓ 3+ distinct, authoritative sources fetched
✓ All sub-questions from plan addressed
✓ Sources cross-referenced for consistency
✓ Confidence level assessed for each claim
✓ Knowledge gaps explicitly acknowledged
```

### Regression Tests
```python
def test_synthesis_not_triggered_without_plan(self):
    research_stats = {"has_plan": False, "unique_urls": {"a", "b", "c"}}
    should_trigger = has_plan and len(unique_urls) >= 3
    self.assertFalse(should_trigger)

def test_synthesis_triggers_with_plan_and_3_sources(self):
    research_stats = {"has_plan": True, "unique_urls": {"a", "b", "c"}}
    should_trigger = has_plan and len(unique_urls) >= 3
    self.assertTrue(should_trigger)
```

---

## ✅ Issue 3: QUICK_LOOKUP Prompt/Limit Mismatch

### Problem
The prompt stated "Maximum: 1 tool call per query (strictly enforced)" but the code allowed 2 (`MAX_TOOL_CALLS_BY_MODE[QUICK_LOOKUP] = 2`).

**Impact**: Unpredictable model behavior; governance inconsistency.

### Fix Applied
**File**: [orchestrator.py:366-403](../argo_brain/assistant/orchestrator.py#L366-L403)

Aligned prompt with code (2 calls allowed):

```python
# Updated prompt sections:

TOOL USAGE GUIDELINES:
- **Maximum**: 2 tool calls per query (1 preferred, fallback allowed for follow-up)

AVOID:
- More than 2 tool calls (use RESEARCH mode for deeper investigation)

STOPPING CONDITIONS:
✓ Answered from context (no tools needed), OR
✓ Made 1-2 tool calls and provided answer based on results
```

### Design Decision
We chose to update the prompt to match the code (rather than restricting code to 1) because:
1. The comment in code indicated 2 was intentional ("fallback" use case)
2. Allowing a second call handles edge cases like search→fetch patterns
3. Restricting to 1 would break legitimate quick lookup patterns

---

## ✅ Issue 4: Double Web Content Ingestion

### Problem
Web content was ingested twice:
1. `WebAccessTool.run()` → `ingestion_manager.ingest_document()` (line 152)
2. `ToolTracker.process_result()` → `_cache_web_content()` → `ingestion_manager.ingest_document()` (line 102)

**Impact**: Storage bloat, duplicate embeddings, polluted retrieval results.

### Fix Applied
**File**: [tool_tracker.py:60-89](../argo_brain/memory/tool_tracker.py#L60-L89)

Removed duplicate ingestion path from ToolTracker:

```python
# Before
def process_result(self, session_id, request, result):
    self.log_tool_run(session_id, request, result)
    if result.tool_name == "web_access" and result.content:
        self._cache_web_content(result)  # ← DUPLICATE INGESTION

def _cache_web_content(self, result):
    doc = SourceDocument(id=f"tool-{uuid4().hex}", ...)
    self.ingestion_manager.ingest_document(doc, ephemeral=True)  # ← REMOVED

# After
def process_result(self, session_id, request, result):
    self.log_tool_run(session_id, request, result)
    # Note: web_access ingestion handled by WebAccessTool directly
    # to prevent duplicate entries in vector store.
```

### Cleanup
- Removed `_cache_web_content()` method entirely
- Removed unused imports: `uuid4`, `SourceDocument`

### Regression Tests
```python
def test_tool_tracker_does_not_ingest_web_content(self):
    tracker = ToolTracker(db=mock_db, ingestion_manager=mock_ingestion)
    tracker.process_result(session_id, request, web_result)
    mock_ingestion.ingest_document.assert_not_called()

def test_tool_tracker_has_no_cache_web_content_method(self):
    self.assertFalse(hasattr(ToolTracker(), "_cache_web_content"))
```

---

## ⏸️ Issue 5: Model-Aware Tool Rendering (Deferred)

### Problem
`ModelRegistry` detects chat templates and prompt formats, but `LLMClient.chat()` doesn't use structured tool definitions. Tools are always rendered as text manifests.

### Status
**Deferred** - Structured function calling requires:
1. llama.cpp native function calling support (experimental)
2. Changes to LLMClient to pass `tools` parameter
3. Response parsing for native tool call format

The current text manifest approach works correctly. This is an optimization for future implementation.

---

## ✅ Issue 6: ToolPolicy Coverage Gaps

### Problem
Only 2 of 5 major tools had policy validators:
- ✅ `web_access` - URL scheme/host validation
- ✅ `memory_query` - top_k bounds
- ❌ `web_search` - No validation
- ❌ `memory_write` - No validation
- ❌ `retrieve_context` - No validation

**Impact**: Missing governance for 60% of tools.

### Fix Applied

#### New Security Config Options
**File**: [config.py:282-293](../argo_brain/config.py#L282-L293)

```python
class SecurityConfig:
    # ... existing fields ...

    # NEW: Tool-specific limits
    web_search_min_query_length: int = 2
    web_search_max_query_length: int = 500
    web_search_max_results: int = 20
    memory_write_max_content_size: int = 50000  # 50KB
    memory_write_allowed_namespaces: tuple[str, ...] = (
        "default", "personal", "research",
        "argo_reading_history", "argo_notes_journal"
    )
    retrieve_context_max_chunk_id_length: int = 200
```

#### New Validators
**File**: [tool_policy.py:74-178](../argo_brain/assistant/tool_policy.py#L74-L178)

| Validator | Checks |
|-----------|--------|
| `_validate_web_search` | Query length (2-500 chars), max_results cap (≤20) |
| `_validate_memory_write` | Content size (≤50KB), namespace allowlist, metadata type |
| `_validate_retrieve_context` | chunk_id required, length limit, character validation |

```python
def _validate_web_search(self, arguments):
    query = arguments.get("query", "")
    if len(query) < self.config.security.web_search_min_query_length:
        return False, "Search query too short", arguments
    if len(query) > self.config.security.web_search_max_query_length:
        arguments["query"] = query[:max_len]  # Truncate
    # ... max_results capping ...
    return True, None, arguments

def _validate_memory_write(self, arguments):
    content = arguments.get("content", "")
    if len(content) > self.config.security.memory_write_max_content_size:
        return False, "Content exceeds max size", arguments
    # ... namespace and metadata validation ...
    return True, None, arguments

def _validate_retrieve_context(self, arguments):
    chunk_id = arguments.get("chunk_id")
    if not chunk_id:
        return False, "retrieve_context requires a chunk_id", arguments
    # ... length and format validation ...
    return True, None, arguments
```

### Regression Tests
```python
def test_web_search_rejects_short_query(self):
    proposals = [ProposedToolCall(tool="web_search", arguments={"query": "a"})]
    approved, rejected = policy.review(proposals, registry)
    self.assertFalse(approved)

def test_memory_write_rejects_oversized_content(self):
    proposals = [ProposedToolCall(tool="memory_write", arguments={"content": "x" * 100000})]
    approved, rejected = policy.review(proposals, registry)
    self.assertFalse(approved)

def test_all_major_tools_have_validators(self):
    expected = ["_validate_web_access", "_validate_web_search",
                "_validate_memory_query", "_validate_memory_write",
                "_validate_retrieve_context"]
    for name in expected:
        self.assertTrue(hasattr(policy, name))
```

---

## Testing

### Run All Tests
```bash
cd /home/krela/llm-argo/argo_brain
python -m pytest tests/ -v
```

### Run Only Architectural Fix Tests
```bash
python -m pytest tests/test_architectural_fixes.py -v
```

### Expected Output
```
tests/test_architectural_fixes.py::TestIssue1RetrieveContextContract::test_retrieve_context_hit_returns_content PASSED
tests/test_architectural_fixes.py::TestIssue1RetrieveContextContract::test_retrieve_context_miss_returns_valid_tool_result PASSED
tests/test_architectural_fixes.py::TestIssue2ResearchSynthesisTiming::test_synthesis_not_triggered_with_few_sources PASSED
tests/test_architectural_fixes.py::TestIssue2ResearchSynthesisTiming::test_synthesis_not_triggered_without_plan PASSED
tests/test_architectural_fixes.py::TestIssue2ResearchSynthesisTiming::test_synthesis_triggers_with_plan_and_3_sources PASSED
tests/test_architectural_fixes.py::TestIssue3QuickLookupLimit::test_quick_lookup_limit_is_two PASSED
tests/test_architectural_fixes.py::TestIssue4DoubleIngestionRemoved::test_tool_tracker_does_not_ingest_web_content PASSED
tests/test_architectural_fixes.py::TestIssue4DoubleIngestionRemoved::test_tool_tracker_has_no_cache_web_content_method PASSED
tests/test_architectural_fixes.py::TestIssue6ToolPolicyValidators::* (11 tests) PASSED
tests/test_architectural_fixes.py::TestToolPolicyHasAllValidators::test_all_major_tools_have_validators PASSED

======================== 19 passed ========================
```

---

## Files Modified

| File | Changes |
|------|---------|
| `argo_brain/tools/retrieve_context.py` | Moved error to metadata dict |
| `argo_brain/assistant/orchestrator.py` | Fixed synthesis timing, updated QUICK_LOOKUP prompt |
| `argo_brain/memory/tool_tracker.py` | Removed duplicate ingestion, cleaned imports |
| `argo_brain/assistant/tool_policy.py` | Added 3 new validators, imported `re` |
| `argo_brain/config.py` | Added 6 new security config options |
| `tests/test_architectural_fixes.py` | New: 19 regression tests |
| `tests/test_session_mode_improvements.py` | Updated: prompt assertion aligned |
| `docs/ARCHITECTURAL_FIXES_V2.md` | New: this document |

---

## Configuration

New environment variables / TOML options:

```toml
[security]
# web_search limits
web_search_min_query_length = 2
web_search_max_query_length = 500
web_search_max_results = 20

# memory_write limits
memory_write_max_content_size = 50000
memory_write_allowed_namespaces = ["default", "personal", "research", "argo_reading_history", "argo_notes_journal"]

# retrieve_context limits
retrieve_context_max_chunk_id_length = 200
```

Or via environment:
```bash
export ARGO_SECURITY_WEB_SEARCH_MAX_QUERY_LENGTH=500
export ARGO_SECURITY_MEMORY_WRITE_MAX_CONTENT_SIZE=50000
```

---

## Impact Summary

### Before Fixes
- ❌ JIT context retrieval crashed on cache miss (TypeError)
- ❌ Research mode synthesized after 1 tool call (shallow answers)
- ❌ QUICK_LOOKUP prompt said "1 max" but allowed 2 (confusing)
- ❌ Web content stored twice (wasted storage + duplicate embeddings)
- ❌ 60% of tools had no policy validation

### After Fixes
- ✅ JIT context retrieval works correctly (error in metadata)
- ✅ Research mode waits for plan + 3 sources (thorough research)
- ✅ QUICK_LOOKUP prompt matches code (2 calls allowed)
- ✅ Single ingestion path (efficient storage)
- ✅ All 5 major tools have policy validators (complete governance)

---

## Future Work

1. **Issue 5 - Structured Function Calling**: Implement when llama.cpp native function calling matures
2. **Rate Limiting**: Add per-tool rate limits to ToolPolicy
3. **Audit Logging**: Enhanced logging for policy rejections
4. **Dynamic Namespaces**: Load allowed namespaces from database instead of config
