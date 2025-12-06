# Argo Brain

Argo Brain is a personal AI assistant that runs entirely locally via `llama-server` (llama.cpp). It ingests your personal browsing data, web articles, and YouTube transcripts into a persistent ChromaDB vector database, and maintains layered conversational memory so the assistant can remember context across sessions.

## Key Features

- **6-Layer Memory Architecture**: Short-term conversation buffer, rolling summaries, autobiographical memory, archival RAG, web cache, and tool results
- **Research Mode**: Planning-first architecture with multi-phase research workflows (planning → execution → synthesis)
- **Tool System**: Extensible tools for web search (DuckDuckGo), web access (trafilatura), and memory operations
- **Session Modes**: QUICK_LOOKUP (fast, max 2 tools), RESEARCH (deep, max 10 tools), INGEST (archival)
- **Trust-Based Storage**: Content classified by trust level (personal/web/tool) for appropriate retention
- **Local-First**: All data stored locally; no external API calls except web search/access

## Project Layout

```
argo_brain/
├── argo_brain/                    # Python package
│   ├── config.py                  # Centralized paths, LLM config, memory tunables
│   ├── runtime.py                 # AppRuntime dependency injection factory
│   ├── llm_client.py              # OpenAI-compatible HTTP client for llama.cpp
│   ├── embeddings.py              # SentenceTransformer wrapper (BAAI/bge-m3)
│   ├── rag.py                     # RAG ingestion & retrieval helpers
│   ├── log_setup.py               # Logging configuration
│   ├── logging_utils.py           # LLM-readable compact logging tags
│   ├── model_prompts.py           # Model-specific prompt templates
│   ├── model_registry.py          # Model auto-detection and configuration
│   ├── tokenizer.py               # Tokenization utilities
│   ├── assistant/                 # ArgoAssistant orchestrator, ResearchStats, ToolPolicy
│   ├── memory/                    # MemoryDB, MemoryManager, SessionManager, ToolTracker
│   ├── core/                      # Core abstractions
│   │   ├── memory/                # IngestionManager, SessionMode, SourceDocument
│   │   └── vector_store/          # VectorStore interface + ChromaDB implementation
│   ├── tools/                     # Tool protocol, WebSearch, WebAccess, MemoryQuery
│   ├── security/                  # TrustLevel system, injection detection
│   ├── utils/                     # Prompt sanitizer, JSON helpers
│   └── vector_store/              # Legacy shim (re-exports from core/vector_store)
├── scripts/                       # CLI entry points (chat_cli, run_tests, rag_core, etc.)
├── tests/                         # Unit and integration tests
├── examples/                      # Example prompts/notebooks
├── plans/                         # Work-in-progress notes and plans
├── notes/                         # Daily work logs (YYYY-MM-DD.md format)
├── data_raw/                      # Raw ingested artifacts (generated)
├── vectordb/                      # Chroma vector store data (generated)
├── docs/                          # Architecture and design documentation
├── argo.toml                      # Configuration file
├── requirements.txt               # Python dependencies
├── CHANGELOG.md                   # Release history
└── test_results.json              # Test summaries (generated)
```

## Setup (WSL Ubuntu)

### 1. Activate Python Virtual Environment

```bash
cd /home/krela/llm-argo/argo_brain
source ~/venvs/llm-wsl/bin/activate  # or your existing virtualenv
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Review Configuration

Edit `argo.toml` to customize paths and LLM settings:

```toml
[data]
root = "/home/krela/llm-argo/.argo_data"
state_dir = "/home/krela/llm-argo/.argo_data/state"
data_raw_path = "/home/krela/llm-argo/.argo_data/data_raw"
models_root = "/mnt/d/llm/models"

[vector_store]
backend = "chroma"
path = "/home/krela/llm-argo/.argo_data/vectordb"

[llm]
base_url = "http://127.0.0.1:8080/v1/chat/completions"
model = "local-llm"
model_name = "qwen3-coder-30b"
temperature = 0.7
top_p = 0.8
top_k = 20
repetition_penalty = 1.05
max_tokens = 16384
```

Override any setting via `ARGO_*` environment variables.

### 4. Configure Windows Username (for Chrome history)

```bash
export WINDOWS_USERNAME="YourWindowsUser"
```

### 5. Start llama-server

```bash
cd /home/krela/llm-argo/llama.cpp
./build/bin/llama-server \
  -m ~/llm/models/qwen3-coder-30b-unsloth/Qwen3-Coder-30B-A3B-Instruct-UD-Q6_K_XL.gguf \
  --ctx-size 8192 \
  --batch-size 1024 \
  --n-gpu-layers 999 \
  --temp 0.3 \
  --port 8080 \
  --top-k 20 \
  --min-p 0.01 \
  --top-p 0.8 \
  -fa 'on' \
  --host 127.0.0.1
```

## Usage

### Interactive Chat

```bash
python scripts/chat_cli.py                          # Random session
python scripts/chat_cli.py --session mysession      # Named session
python scripts/chat_cli.py --mode research          # Research mode

### Browser Chat (Tailnet)

- Start web service: `python -m scripts.chat_service --host 0.0.0.0 --port 3210` (optional: set `ARGO_WEB_TOKEN`; TLS via `ARGO_WEB_TLS_CERT/KEY` if desired).
- Tailnet test: `curl -H "Authorization: Bearer $ARGO_WEB_TOKEN" http://<tailnet-host>:3210/health` (omit header if token unset).
- UI: open `http://<tailnet-host>:3210/` from another Tailscale device (e.g., iPad). Enter the token if set, choose a session ID to share memory with the CLI.
```

**REPL Commands:**

| Command     | Description                                       |
|-------------|---------------------------------------------------|
| `:new`      | Start new session                                 |
| `:facts`    | List profile facts                                |
| `:summary`  | Show session summary                              |
| `:webcache` | Show recent tool/browse runs                      |
| `:stats`    | Session statistics (tool usage, message counts)   |
| `:tools`    | List available tools                              |
| `:tool`     | Run tool: `:tool <name> <query_or_url>`          |
| `:help`     | Show help                                         |
| `:quit`     | Exit                                              |

### Session Modes

- **`quick_lookup`** (default): Fast answers with minimal tool usage (max 2 calls)
- **`research`**: Deep research with planning-first architecture, max 10 tool calls, synthesis with citations
- **`ingest`**: Archive and summarize user-provided material

Quick Lookup behavior:
- Memory-first: tries to answer from stored context before using tools.
- Clarify-first: asks for clarification on ambiguous or context-only prompts instead of guessing.
- External facts/docs: may run a single `web_search` (max_results≈5) and, for docs, `web_access` to fetch a page; responses include citations.
- Deep/broad asks: suggests switching to RESEARCH mode rather than stretching the 2-call budget.
- Safety: refuses PII, local file/path or dangerous payloads; prompt-injection quotes are summarized as attacks with no tools.

### Ingestion CLIs

```bash
# Ingest a web article
python scripts/rag_core.py https://example.com/article

# Ingest YouTube transcript
python scripts/youtube_ingest.py https://youtube.com/watch?v=...

# Process Chrome history
python scripts/history_ingest.py

# Query the knowledge base
python scripts/rag_core.py "What did I read about machine learning?"
```

## Memory Architecture

Argo builds prompts by fusing 6 memory sources:

1. **Short-term buffer**: Last K=6 user/assistant turns (SQLite)
2. **Session summary**: Compressed older context, updated every 20 messages
3. **Autobiographical memory**: Long-lived personal facts (ChromaDB)
4. **Archival RAG**: Reading history, YouTube transcripts, notes
5. **Web cache**: Ephemeral tool outputs with 7-day TTL
6. **Tool results**: Structured outputs from current conversation

## Tool System

Built-in tools:

- **`web_search`**: DuckDuckGo search, returns URLs and snippets
- **`web_access`**: Fetch and extract web pages (trafilatura)
- **`memory_query`**: Search personal knowledge base with filters
- **`memory_write`**: Store facts to autobiographical memory
- **`retrieve_context`**: Direct chunk lookup by ID

Tools follow a policy-based validation system (`ToolPolicy`) with:
- URL scheme/host validation
- Query length bounds
- Dangerous pattern detection
- Parameter clamping

## Testing


### Unit/Integration Tests (pytest)
```bash
cd /home/krela/llm-argo/argo_brain
source ~/venvs/llm-wsl/bin/activate

# Run all tests with temp directories
ARGO_ROOT=$PWD/.tmpdata \
ARGO_STATE_DIR=$PWD/.tmpdata/state \
ARGO_DATA_RAW_PATH=$PWD/.tmpdata/data_raw \
ARGO_VECTOR_STORE_PATH=$PWD/.tmpdata/vectordb \
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_research_tracker.py -v

# Run with debug logging
ARGO_DEBUG_RESEARCH=true python -m pytest tests/test_research_tracker.py -v
```

### Manual Test Runner (with auto-validation & sandboxed state)
```bash
# Run specific test case
python scripts/run_tests.py --test TEST-005 --auto

# Run with verbose output
python scripts/run_tests.py --test TEST-005 --auto --verbose

# Run with debug mode
ARGO_DEBUG_RESEARCH=true python scripts/run_tests.py --test TEST-005 --auto
```

**Auto-validation**: In `--auto`, the runner records per-turn responses to `/tmp/test_<id>_<session>_turnN.txt`, gathers tool runs/profile facts from a sandboxed SQLite DB, and applies heuristic checks per test (tool usage, citations, safety refusals, memory vs web). Failures include a reason for fast triage. Tests use an isolated in-memory vector store and temp SQLite, so profile facts and embeddings do not touch your real `.argo_data` state.

### Test Categories
- `test_research_tracker.py` - ResearchStats tracking (17 tests)
- `test_architectural_fixes.py` - Regression tests for Issues 1-6
- `test_session_mode_improvements.py` - Session mode validation
- `test_tool_renderer.py` - Tool rendering formats
- `test_ingestion.py` - IngestionManager functionality

## Debug Modes

```bash
export ARGO_DEBUG_RESEARCH=true   # Research mode logging
export ARGO_DEBUG_TOOLS=true      # Tool execution logging
export ARGO_DEBUG_ALL=true        # All debug logging
```

## Data Locations

| Item | Path |
|------|------|
| Configuration | `argo.toml` |
| SQLite DB | `.argo_data/state/argo_memory.sqlite3` |
| Vector DB | `.argo_data/vectordb/` |
| Raw data | `.argo_data/data_raw/` |
| Test data | `.tmpdata/` |

## Requirements

- Python 3.10+
- llama.cpp / llama-server
- WSL2 Ubuntu (for Windows integration)
- Access to `/mnt/c` (Chrome profile) and `/mnt/d` (storage)

**Python packages**: chromadb, sentence-transformers, trafilatura, youtube-transcript-api, requests, tomli, numpy, ddgs

## Documentation

- [CLAUDE.md](CLAUDE.md) - Instructions for Claude Code
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [docs/](docs/) - Architecture and design docs
- [tests/manual_test_cases.md](tests/manual_test_cases.md) - Manual test documentation

## Troubleshooting

- **Slow model downloads**: Set `HF_HOME=/mnt/d/huggingface` and pre-download models
- **Connection refused**: Ensure llama-server is running on port 8080
- **Chrome history locked**: Close Chrome before running history_ingest.py


### Major Flows

1. **Chat Flow**: User message → MemoryManager assembles 6-layer context → ArgoAssistant builds prompt → LLMClient calls llama-server → Tool execution loop → Response
2. **Tool Execution**: ToolPolicy validates → Tool executes → ToolTracker logs → Results cached for next prompt
3. **Research Mode**: Planning phase → Tool execution phase (3+ sources) → Synthesis phase
4. **Ingestion Flow**: SourceDocument → IngestionManager chunks/embeds → ChromaVectorStore stores

### Key Design Patterns

- **Dependency Injection**: `AppRuntime` factory wires all services
- **6-Layer Memory**: Short-term buffer, session summary, autobiographical memory, archival RAG, web cache, tool results
- **Trust Levels**: PERSONAL_HIGH, WEB_UNTRUSTED, TOOL_OUTPUT
- **Session Modes**: QUICK_LOOKUP (fast, max 2 tools), RESEARCH (deep, max 10 tools), INGEST (archival)

## Custom Scripts & Tools

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/chat_cli.py` | Interactive REPL | `python scripts/chat_cli.py --session mysession` |
| `scripts/run_tests.py` | Test runner with validation | `python scripts/run_tests.py --test TEST-005 --auto` |
| `scripts/rag_core.py` | RAG ingest/query | `python scripts/rag_core.py https://example.com` |
| `scripts/youtube_ingest.py` | YouTube transcripts | `python scripts/youtube_ingest.py <youtube-url>` |
| `scripts/history_ingest.py` | Chrome history | `python scripts/history_ingest.py` |
| `scripts/cleanup_expired.py` | Clean web cache | `python scripts/cleanup_expired.py` |
| `scripts/monitor_performance.py` | Performance monitoring | `python scripts/monitor_performance.py` |
## Key Files to Understand

### Configuration
- [argo.toml](argo.toml) - Main config (paths, LLM settings, model params)
- [argo_brain/config.py](argo_brain/config.py) - Config loader with env var overrides

### Core Logic
- [argo_brain/assistant/orchestrator.py](argo_brain/assistant/orchestrator.py) - Main AI orchestrator
- [argo_brain/assistant/research_tracker.py](argo_brain/assistant/research_tracker.py) - Research mode tracking
- [argo_brain/memory/manager.py](argo_brain/memory/manager.py) - 6-layer context assembly

### Tools
- [argo_brain/tools/base.py](argo_brain/tools/base.py) - Tool protocol and registry
- [argo_brain/tools/web.py](argo_brain/tools/web.py) - WebAccessTool
- [argo_brain/tools/search.py](argo_brain/tools/search.py) - WebSearchTool

### Vector Store
- [argo_brain/core/vector_store/](argo_brain/core/vector_store/) - Canonical VectorStore interface and implementations
- Note: `argo_brain/vector_store/` is a legacy shim that re-exports from `core/vector_store`

---

## Common Patterns

### Adding a New Tool
```python
# 1. Implement Tool protocol in tools/new_tool.py
class NewTool:
    name = "new_tool"
    description = "..."
    input_schema = {...}

    def run(self, request: ToolRequest) -> ToolResult:
        ...

# 2. Add validator in tool_policy.py
def validate_new_tool(params: dict) -> Tuple[bool, str]:
    ...

# 3. Register in chat_cli.py or orchestrator initialization
registry.register(NewTool())
```

### Extending Session Modes
```python
# 1. Add to SessionMode enum (core/memory/session.py)
# 2. Create prompt method in orchestrator.py
# 3. Add temperature schedule in _get_temperature_for_phase()
# 4. Add max_tokens in _get_max_tokens_for_mode()
# 5. Define tool availability in _get_available_tools_for_mode()
```

---

## Debugging Tips

### Enable Debug Logging
```bash
ARGO_DEBUG_RESEARCH=true python scripts/chat_cli.py
```

### Check Execution Path
Look for logs like:
```
[INFO] Executing 1 tools via batch path
[R:URL] #3/3 ✓ (p=b)
[STATE:->] exec→synth (why=3URL+plan) ✓
```

### Research Mode Not Triggering Synthesis?
Check:
1. `has_plan` is True (research_plan tag present)
2. `unique_urls` count >= 3
3. `synthesis_triggered` is False (not already triggered)

---

### Environment Variables
```bash
# Debug modes
export ARGO_DEBUG_RESEARCH=true   # Research mode logging
export ARGO_DEBUG_TOOLS=true      # Tool execution logging
export ARGO_DEBUG_ALL=true        # All debug logging

# Path overrides (for testing)
export ARGO_ROOT=$PWD/.tmpdata
export ARGO_VECTOR_STORE_PATH=$PWD/.tmpdata/vectordb
```


---
