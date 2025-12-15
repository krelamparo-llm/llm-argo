# CLAUDE.md - Claude Code Instructions for Argo Brain

This file provides context and instructions for Claude Code when working on the Argo Brain project.

---

## Project Overview

You are Claude Code, operating on a local-first AI system called **Argo** (a personal LLM + memory/RAG stack running on the user's own hardware).

Your goals, in order of priority:

1. **Correctness and safety of data / code**
2. **Maintaining architecture and invariants**
3. **Good developer ergonomics**
4. **Speed**

---

## 1. High-level project overview

Argo Brain is a **local-first personal AI assistant** that:

- Talks to a **local LLM server** (currently via `llama.cpp` / `llama-server`, using models stored on the user's machine).
- Ingests:
  - Browser history / web pages
  - YouTube transcripts
  - Other text sources
- Stores them in a **persistent vector database** (currently Chroma, accessed via `argo_brain.vector_store`).
- Provides:
  - A CLI chat interface
  - Ingestion scripts for web/YouTube/etc.
  - A layered memory system (short-term, long-term, archival) on top of the vector store + RAG.

Argo is intended to run locally on a powerful desktop (named **Argo**) and may be accessed remotely (SSH, VS Code remote, etc.). Do **not** assume cloud infrastructure.

---

## 2. Repository layout (mental map)

When exploring or editing, assume roughly this structure:

```
argo_brain/
├── argo_brain/                    # Main Python package
│   ├── config.py                  # Centralized configuration (AppConfig, paths, LLM settings)
│   ├── runtime.py                 # AppRuntime factory for dependency injection
│   ├── llm_client.py              # OpenAI-compatible HTTP client for llama-server
│   ├── embeddings.py              # SentenceTransformer wrapper (BAAI/bge-m3)
│   ├── rag.py                     # RAG ingestion & retrieval helpers
│   ├── log_setup.py               # Logging configuration
│   ├── logging_utils.py           # LLM-readable compact log formatting
│   ├── model_prompts.py           # Model-specific prompt templates
│   ├── model_registry.py          # Model auto-detection and configuration
│   ├── tokenizer.py               # Tokenization utilities
│   │
│   ├── assistant/                 # Orchestration layer
│   │   ├── orchestrator.py        # ArgoAssistant - main AI orchestrator
│   │   ├── research_tracker.py    # ResearchStats - research mode tracking
│   │   └── tool_policy.py         # ToolPolicy - security validation
│   │
│   ├── memory/                    # Conversation and knowledge management
│   │   ├── db.py                  # MemoryDB - SQLite persistence
│   │   ├── manager.py             # MemoryManager - 6-layer context assembly
│   │   ├── session_manager.py     # SessionManager - conversation lifecycle
│   │   └── tool_tracker.py        # ToolTracker - tool audit logging
│   │
│   ├── core/                      # Core abstractions
│   │   ├── memory/                # Document, session, ingestion, decay
│   │   │   ├── session.py         # SessionMode enum
│   │   │   ├── document.py        # SourceDocument class
│   │   │   ├── ingestion.py       # IngestionManager
│   │   │   └── decay.py           # Temporal relevance scoring
│   │   └── vector_store/          # VectorStore interface (canonical location)
│   │       ├── base.py            # VectorStore abstract interface
│   │       ├── factory.py         # Factory for creating VectorStore instances
│   │       ├── chromadb_impl.py   # ChromaVectorStore implementation
│   │       └── memory_impl.py     # InMemoryVectorStore (testing)
│   │
│   ├── tools/                     # Tool system
│   │   ├── base.py                # Tool protocol, ToolRegistry, ToolRequest/Result
│   │   ├── renderer.py            # ToolRenderer (multiple output formats)
│   │   ├── xml_parser.py          # XMLToolParser
│   │   ├── memory.py              # MemoryQueryTool, MemoryWriteTool
│   │   ├── search.py              # WebSearchTool
│   │   ├── web.py                 # WebAccessTool
│   │   ├── retrieve_context.py    # RetrieveContextTool
│   │   └── db.py                  # DatabaseQueryTool
│   │
│   ├── security/                  # Trust levels and injection detection
│   │   ├── trust.py               # TrustLevel enum
│   │   └── injection.py           # Prompt injection detection
│   │
│   ├── utils/                     # Utilities
│   │   ├── prompt_sanitizer.py    # Prompt validation
│   │   └── json_helpers.py        # JSON extraction helpers
│   │
│   └── vector_store/              # Legacy shim (re-exports from core/vector_store)
│
├── scripts/                       # CLI entry points
│   ├── chat_cli.py                # Interactive REPL
│   ├── run_tests.py               # Test runner with strict validation
│   ├── rag_core.py                # RAG ingestion & query
│   ├── youtube_ingest.py          # YouTube transcript ingestion
│   └── history_ingest.py          # Chrome history ingestion
│
├── tests/                         # Unit and integration tests
├── docs/                          # Architecture and design documentation
├── notes/                         # Daily work logs (YYYY-MM-DD.md format)
├── argo.toml                      # Configuration file
└── requirements.txt               # Python dependencies
```

**Key notes:**
- `runtime.py` is a single file (not a directory) that provides `AppRuntime` and `create_runtime()`
- Vector store: canonical implementation is in `core/vector_store/`; `vector_store/` at package root is a legacy shim
- Configuration: `config.py` loads from `argo.toml` + environment variables (no separate config directory)

---


## 3. General behavior guidelines

When working in this repo:

1. **Explore before editing**
   - Use file tools (`@path/to/file`, or equivalent) to read relevant modules end-to-end.
   - Summarize what the existing code does before proposing changes.
   - For non-trivial tasks, **first produce a short plan** (steps, files, tests).

2. **Prefer small, reviewable diffs**
   - Make changes in **small, logically coherent steps**.
   - Avoid giant multi-file refactors unless explicitly requested.
   - When refactoring, keep behavior identical and tests passing.

3. **Use tests and commands, not guesses**
   - Prefer running tests / scripts over speculating.
   - Always run appropriate tests or smoke checks after making changes.

4. **Avoid destructive actions**
   - Do **not** delete data directories (e.g. vector DB storage) or user data.
   - Do **not** run destructive shell commands without explicit user instruction
     (e.g. `rm -rf`, `drop` DB, mass rewrite of models).

5. **Respect configuration**
   - Do not hardcode machine-specific paths (like `D:\` or `/mnt/d`) in code.
   - Use configuration files, environment variables, or runtime config helpers.

---

## 4. Coding conventions

Follow these conventions unless codebase clearly uses something else:

### Python

- Use **type hints** for all new or modified public functions/methods.
- Prefer **dataclasses** or simple Pydantic-style configs for structured config data.
- Keep functions reasonably small and focused.

### Style & formatting

- **No linters/formatters are currently configured** in this project (no `pyproject.toml`, `ruff.toml`, etc.)
- Follow PEP8 style manually:
  - 4-space indentation
  - Max line length ~100 characters
  - Group imports: stdlib, third-party, local modules
- If formatters are added in the future, use them consistently

### Logging & errors

- Use the project’s logging setup (`argo_brain.log_setup`) rather than raw `print` for non-trivial output.
- Raise specific exceptions where appropriate.
- Don’t swallow exceptions silently; either handle them or log them.

### Dependencies

- Avoid adding new heavy dependencies unless strictly necessary.
- If you must add a dependency:
  - Explain why in the PR/plan.
  - Add it to the appropriate dependency file (`requirements.txt`, `pyproject.toml`, etc.).
  - Prefer well-maintained libraries.

---


## 5. How to run things

When you need to run code, prefer these patterns:

- **Chat CLI**:
  - Run the interactive chat against the local LLM:
    - `python scripts/chat_cli.py`
    - Or whatever command is documented in `README.md`.

- **Ingestion scripts**:
  - Use the provided `scripts/*.py` entrypoints rather than ad-hoc snippets when possible.

If you’re unsure which command to use:

1. Check `README.md` and any `docs/` files.
2. Scan `pyproject.toml` / `setup.cfg` / `Makefile` for common tasks.
3. Describe your inferred plan in the chat before running commands.

---

## 6. Memory, RAG, and vector store invariants

Argo's main value comes from its memory/RAG pipeline. When touching related code, preserve these invariants:

### 6-Layer Memory Architecture

The system assembles context from 6 sources (see `memory/manager.py`):

1. **Short-term buffer**: Last K=6 user/assistant turns (SQLite `messages`)
2. **Session summary**: Compressed older context (SQLite `session_summaries`)
3. **Autobiographical memory**: Personal facts (ChromaDB `argo_autobiographical_memory`)
4. **Archival RAG**: Reading history, YouTube, notes (ChromaDB namespaces)
5. **Web cache**: Ephemeral tool outputs (ChromaDB `argo_web_cache`, TTL=7 days)
6. **Tool results**: Structured outputs from tool execution

### Separation of concerns

- `rag.py`: Chunking, embedding, and retrieval helpers
- `core/memory/ingestion.py`: `IngestionManager` handles document → chunks → vector store
- `memory/manager.py`: `MemoryManager` assembles 6-layer context for prompts
- `memory/session_manager.py`: Conversation lifecycle, summarization
- `memory/tool_tracker.py`: Tool execution audit logging

### Vector store abstraction

- **Canonical location**: `argo_brain.core.vector_store` (base, factory, implementations)
- **Legacy shim**: `argo_brain.vector_store` re-exports from `core.vector_store` for backwards compatibility
- All direct vector DB access should go through the abstraction layer
- Do not scatter raw Chroma access across the codebase
- If adding a new vector DB, implement `VectorStore` interface in `core/vector_store/`

### Memory layering rules

- Session-level buffers, summaries, and long-term storage are separate concerns
- Preserve clear interfaces for reading/writing session memory
- Explicit control over what gets promoted to long-term memory
- If modifying promotion criteria, document the new behavior in docstrings

### Non-destructive ingestion

- Ingestion should **append** to memory/vector store, not silently overwrite or drop data
- Pruning or compaction must be implemented explicitly and safely (e.g., `scripts/cleanup_expired.py`)

---

## 7. Tools and agent behavior

Argo itself exposes tools internally (web fetch, memory, etc.), but from within this repo you should follow these rules:

1. **Use existing tools first**
   - When you need web content, use the existing `tools/web.py` (or the project’s web tooling), not random HTTP clients unless necessary.
   - For memory operations, use `tools/memory.py` and the defined memory manager APIs.

2. **Do not invent tools silently**
   - If a new tool is needed, propose:
     - The tool’s purpose and narrow scope.
     - Its interface (input/output types).
     - Where it should live (likely under `argo_brain/tools/`).
   - Implement it as a thin adapter over existing core logic (e.g. RAG/memory/runtime).

3. **Avoid tight coupling to specific LLM implementations**
   - Keep the core Argo logic agnostic to the specific LLM backend.
   - Use runtime/config abstractions to specify which model / server endpoint is active.

---


## 8. Editing rules & workflows

Use these workflows by default:

### For any non-trivial change

1. **Plan**
   - Read relevant files.
   - Summarize current behavior in your own words.
   - Propose a short, numbered implementation plan (files, steps, tests).

2. **Implement step-by-step**
   - Implement **one plan step at a time**.
   - After each step:
     - Show the diff.
     - Run the relevant tests or a smoke check if practical.

3. **Tests**
   - When modifying behavior, add or update tests.
   - Prefer **test-first** when possible:
     - Add failing tests that encode expected behavior.
     - Then implement code to make them pass.

4. **Documentation**
   - Update docstrings and any relevant docs under `README.md` or `docs/` when behavior changes.
   - For significant design decisions, add documentation to `docs/` (no formal ADR structure currently exists).

### For small changes

- Typo fixes, minor refactors, or trivial bug fixes can be done directly, but still:
  - Keep diffs small.
  - Run at least a targeted test or script where easy.

---

## 9. Things you should not do without explicit permission

Do **not**:

- Rewrite the entire repository or large subsystems in a single step.
- Remove or weaken safety checks, input validation, or access control logic.
- Add network calls or external dependencies that exfiltrate data outside the local machine.
- Hardcode machine-specific paths or credentials.
- Run destructive shell commands (`rm -rf`, DB drops, mass file moves) unless the user explicitly instructs you to.

---

## 10. When unsure

If you are unsure about:

- The intent of a module,
- The correct place to put new functionality,
- Whether a change is backward compatible,

…then:

1. State your uncertainty explicitly.
2. Propose a small, conservative change or a short design note.
3. Wait for user confirmation before performing large refactors or migrations.

Always bias toward **clarity, safety, and small steps** over cleverness or sweeping changes.
---
### Error Handling
- Use specific exceptions, not bare `except:`
- Log errors with context (session_id, tool_name, etc.)
- Return `ToolResult` with error info in metadata, not raised exceptions

### Logging
- Use structured logging with `extra={}` dict for context
- Use LLM-readable compact tags from `logging_utils.py` (e.g., `[R:URL]`, `[STATE:->]`)
- Debug logging controlled by environment variables (`ARGO_DEBUG_*`)

### Debug Environment Variables
- `ARGO_DEBUG_RESEARCH` - Research mode logging
- `ARGO_DEBUG_TOOLS` - Tool execution logging
- `ARGO_DEBUG_ALL` - All debug logging
- `ARGO_DEBUG_PROMPT` - Dump full prompts to `/tmp/argo_prompt_*.txt`

---

## Daily Work Hygiene

### Use notes/ Instead of docs/

Instead of creating uniquely-named documents in `docs/`, summarize daily work into:
```
notes/YYYY-MM-DD.md
```

### Daily Note Format
```markdown
# YYYY-MM-DD - [Brief Topic]

## Summary
- What was accomplished today
- Key decisions made

## Changes Made
- file1.py: Added X functionality
- file2.py: Fixed Y bug

## TODOs
- [ ] Next step 1
- [ ] Next step 2

## Notes
Any additional context or thoughts
```

### When to Use docs/
- Architecture documentation that won't change frequently
- API documentation
- Onboarding guides

---
