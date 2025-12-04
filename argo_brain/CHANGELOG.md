# Changelog

All notable changes to Argo Brain are documented in this file.

## [Unreleased] - 2025-12-03

### Added - LLM-Readable Logging System

**Token-Efficient Logging for LLM Consumption**
- New `logging_utils.py` module with compact semantic tags
- LogTag enum: `R:URL`, `R:SRCH`, `R:SYNTH`, `STATE:->`, `E:BATCH`, `D:`
- 61% token reduction in log output (273 → 105 tokens per workflow)
- Progress indicators with milestones: `[R:URL] #3/3 ✓`
- Decision logging: `[D:] synth=Y (p=Y, u=3, t=N)`
- State transitions: `[STATE:->] exec→synth (why=3URL+plan) ✓`

### Added - Comprehensive Debugging Infrastructure

**Phase 1: Core Architecture Improvements**
- `ResearchStats` dataclass for centralized research tracking
- Execution path tracing (batch vs individual tool calls)
- Enhanced test validation with 6 strict checks for RESEARCH mode
- Eliminated code duplication between execution paths

**Phase 2: Testing & Debug Tools**
- 17 integration tests for ResearchStats (100% coverage)
- Debug mode flags via environment variables:
  - `ARGO_DEBUG_RESEARCH` - Research mode logging
  - `ARGO_DEBUG_TOOLS` - Tool execution logging
  - `ARGO_DEBUG_ALL` - All debug logging
- `DebugConfig` class in config.py

**Impact**
- Debug time reduced from 2 hours to 15 minutes (87.5% improvement)
- TEST-005 bug class permanently eliminated
- All research mode tests passing with strict validation

### Added - Session Mode Architecture Improvements

**Comprehensive Mode Prompts**
- QUICK_LOOKUP: 58 lines of guidance (was 10 words)
- INGEST: 88 lines with 4-step workflow (was 11 words)
- RESEARCH: 159 lines with multi-phase framework

**Progressive Temperature Schedule**
- QUICK_LOOKUP: 0.3 (initial) → 0.5 (after tools)
- RESEARCH: 0.4 (planning) → 0.2 (tools) → 0.7 (synthesis)
- INGEST: 0.5 (structured summaries)

**Mode-Specific Max Tokens**
- QUICK_LOOKUP: 1024 (concise answers)
- RESEARCH: 4096 (long synthesis)
- INGEST: 2048 (structured summaries)

**Dynamic Tool Availability**
- QUICK_LOOKUP: web_search, web_access, memory_query, retrieve_context (no memory_write)
- RESEARCH Planning: No tools (plan first)
- RESEARCH Exploration: web_search, web_access, retrieve_context
- RESEARCH Synthesis: memory_write, memory_query, retrieve_context
- INGEST: web_access, memory_write, memory_query, retrieve_context (no web_search)

### Added - Tool Renderer System

**Multi-Format Tool Rendering**
- TEXT_MANIFEST: Standard text format
- QWEN_XML: XML-style for Qwen models
- CONCISE_TEXT: Minimal token usage
- OPENAI_TOOLS / ANTHROPIC_TOOLS: Structured formats (future)

**Tool Registry Enhancements**
- `filter_tools` parameter for mode-specific manifests
- `DefaultToolRenderer` class

### Changed - Research Mode Orchestration

**Planning-First Architecture**
- Mandatory `<research_plan>` before tool execution
- Research question breakdown into sub-questions
- Explicit search strategies and success criteria

**Synthesis Trigger Conditions**
- Requires: has_plan AND unique_urls >= 3 AND not synthesis_triggered
- Prevents premature synthesis
- Tracks execution path for each tool call

**XML Tool Parsing Improvements**
- Normalization for truncated XML tags
- Better handling of malformed tags
- Prevents nested XML generation in research plans

### Changed - Architectural Fixes (Issues 1-6)

**Issue 1: ToolResult Contract**
- Removed 'error' kwarg, use metadata instead
- Standardized error reporting

**Issue 2: Research Mode Synthesis**
- Fixed synthesis trigger (requires plan + 3 sources)
- Centralized tracking via ResearchStats

**Issue 3: QUICK_LOOKUP Prompt Alignment**
- Clear 1-2 tool call maximum
- Priority order guidance

**Issue 4: Double Web Ingestion**
- Removed duplicate ingestion in ToolTracker
- WebAccessTool handles caching directly

**Issue 6: ToolPolicy Coverage**
- Validators for all tools (web_access, web_search, memory_query, memory_write, retrieve_context)
- URL scheme/host validation
- Query length bounds
- Parameter clamping

### Fixed

- Research plan duplication in response text
- Truncated XML tag normalization
- Tool execution retry logic
- Logging initialization warnings
- Empty prompt guard-rails

### Documentation

- CLAUDE.md - Claude Code instructions
- SESSION_MODE_IMPLEMENTATION_SUMMARY.md - Mode architecture details
- LLM_LOGGING_IMPLEMENTATION.md - Logging system documentation
- DEBUGGING_IMPROVEMENTS.md - Full debugging proposal
- PHASE_1_AND_2_COMPLETE.md - Implementation summary

---

## [2025-12-02] - Best-in-Class Research Mode

### Added - Best-in-Class Research Mode

**Planning-First Architecture**
- Mandatory `<research_plan>` generation before tool execution
- Research question breakdown into sub-questions
- Explicit search strategies and success criteria
- Expected source type specification (academic/industry/docs)

**Self-Reflection & Quality Assessment**
- Stage-specific reflection prompts after each tool call
- Source quality evaluation (authority, recency, primary vs secondary)
- Cross-reference checking for contradictions
- Coverage assessment against original plan

**Stopping Conditions Enforcement**
- Real-time checklist with 6 criteria
- Progress feedback prevents premature conclusions
- Explicit plan creation requirement
- Minimum 3 distinct sources requirement
- Mandatory confidence assessment (High/Medium/Low)
- Mandatory knowledge gap identification

**Iterative Query Refinement**
- Search query evolution tracking
- Refinement suggestions based on gaps
- Display of last 3 search queries used

**Structured Working Memory**
- Research state tracking (sources, queries, plan)
- XML-based context formatting for clarity
- Plan persistence throughout research session

**Multi-Step Reasoning Framework**
- Required XML structure: `<research_plan>`, `<think>`, `<synthesis>`, `<confidence>`, `<gaps>`
- Citation format enforcement: `[Source](URL)`
- Contradiction detection and resolution
- Epistemic uncertainty quantification

### Added - Enhanced Observability

**Structured Tool Execution Logging**
- All tool invocations logged to SQLite `tool_runs` table
- Structured application logs with JSON extras:
  - `tool_name`, `session_id`
  - `input_length`, `output_length`
  - `snippet_count`, `has_snippets`
  - `metadata_keys`

**Error Classification**
- All tool failures logged with:
  - `error_type` (exception class name)
  - `error_message` (truncated to 200 chars)
  - Full context (query, URL, session_id)
- Applied to WebSearchTool and WebAccessTool

**Session Statistics Command**
- New `:stats` command shows:
  - Total message count
  - Summary status
  - Tool usage breakdown (sorted by frequency)
  - Unique tools used

### Changed - Simplified Ingestion API

**IngestionManager Refactoring**
- Replaced 3-value `IngestionPolicy` enum with simple `ephemeral: bool` flag
- Removed `session_mode` and `user_intent` parameters
- Streamlined API: `ingest_document(doc, ephemeral=False)`
- Namespace routing now based purely on `source_type`

**Namespace Strategy**
- `ephemeral=True` → `web_cache` (7-day TTL)
- `ephemeral=False` → namespace from source_type:
  - `web_article` → `web_articles`
  - `youtube_*` → `youtube_history`
  - `note`, `journal` → `notes_journal`

### Changed - Session Management

**Extracted Components**
- `SessionManager`: Conversation lifecycle (messages, summaries)
- `ToolTracker`: Tool execution audit and caching
- `MemoryManager`: Memory extraction only (no longer handles sessions or tools)

**Database Enhancements**
- Added `count_messages_since_summary()` method
- Added `update_session_summary()` alias
- Added `ToolRunRecord` and `SummarySnapshot` dataclasses

### Changed - Tool System

**New Tools**
- `WebSearchTool`: DuckDuckGo/SearXNG integration with query tracking
- Updated import: `ddgs` package (formerly `duckduckgo_search`)

**Enhanced WebAccessTool**
- Structured error logging
- Trust level metadata enforcement (`WEB_UNTRUSTED`)
- Automatic ephemeral caching in `web_cache`

**Tool Execution Limits**
- Research mode: 10 tool calls (up from 3)
- Quick-lookup mode: 3 tool calls (unchanged)

### Changed - Context Formatting

**XML Structure**
- Replaced plain text headers with XML tags:
  - `<session_summary trust="high">...</session_summary>`
  - `<autobiographical>`, `<knowledge_base>`, `<web_cache>`
  - `<chunk id="1" trust="..." source_type="..." url="...">...</chunk>`

### Fixed - Runtime Errors

**Import Errors**
- Removed `IngestionPolicy` import from `tools/memory.py`
- Removed `SessionMode` import from test files

**Method Mismatches**
- Fixed `process_tool_result()` → `process_result()` in orchestrator
- Fixed `request.tool_name` → `result.tool_name` in ToolTracker
- Added missing `count_messages_since_summary()` to MemoryDB

**DuckDuckGo Package**
- Updated to new `ddgs` package with fallback
- Fixed search returning 0 results

### Testing

**Updated Test Suites**
- `test_ingestion.py`: Updated for `ephemeral` parameter
- `test_rag_integration.py`: Removed SessionMode usage
- `test_web_tool.py`: Updated FakeIngestionManager signature
- All 10 tests passing

---

## [Previous] - Initial Release

### Added
- Multi-layer memory architecture (short-term, session summary, autobiographical, web cache)
- Tool system with policy-based approval
- Security framework with TrustLevel enforcement
- Vector store abstraction (ChromaDB backend)
- Session modes (quick-lookup, research, ingest)
- SQLite persistence for messages, summaries, profile facts
- Web access and memory query tools
- Decay scoring for temporal relevance

### Changed
- Centralized configuration in `argo.toml`
- OpenAI-compatible LLM client for llama.cpp

### Infrastructure
- WSL2 Ubuntu environment
- Local llama-server (llama.cpp)
- ChromaDB embedded vector store
- SentenceTransformers embeddings (BAAI/bge-m3)

---

## Release Versioning

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Incompatible API changes
- **MINOR**: Backward-compatible functionality additions
- **PATCH**: Backward-compatible bug fixes

Current status: Pre-1.0 development (API not yet stable)
