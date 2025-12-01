# Changelog

All notable changes to Argo Brain are documented in this file.

## [Unreleased] - 2025-01-30

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

**Backward Compatibility**
- All existing code updated to new API
- SessionMode still used for prompt selection
- No data migration required (no existing data)

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

**Benefits**
- Easier for LLM to parse and cite
- Clear metadata attribution
- Better structured reasoning

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
- All 10 tests passing ✅

**Test API Simplification**
- Removed `FakeLLM` class (no longer needed)
- Simplified IngestionManager initialization

## [Previous] - 2025-01-XX

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
- Moved from `/home/llm-argo` to `/mnt/d/llm/argo_brain` for storage
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
