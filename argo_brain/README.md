# Argo Brain

Argo Brain ingests your personal browsing data, web articles, and YouTube transcripts into a persistent Chroma vector database stored on `/mnt/d`. The scripts run inside WSL Ubuntu and talk to a local `llama-server` so you can ask grounded questions about everything you've read or watched. On top of the archival RAG store, Argo now keeps layered conversational memory so the assistant can remember short-term context, rolling summaries, and long-lived autobiographical facts.

## Project layout

```
/home/llm-argo/argo_brain/
├── argo_brain/             # Python package (config, rag, memory, assistant, etc.)
│   ├── config.py           # Centralized paths, llama-server config, memory tunables
│   ├── llm_client.py       # OpenAI-compatible HTTP client for llama.cpp
│   ├── rag.py              # Retrieval + ingestion helpers shared across scripts
│   ├── embeddings.py       # SentenceTransformer wrapper
│   ├── memory/             # SQLite schema, prompts, MemoryManager
│   └── assistant/          # ArgoAssistant orchestrator
├── scripts/                # Thin CLIs (rag_core, youtube_ingest, history_ingest, chat_cli)
├── requirements.txt        # Python dependency list
├── vectordb/               # Placeholder; actual DB stored on /mnt/d/llm/argo_brain/vectordb
├── data_raw/               # Placeholder; Chrome history copies live on /mnt/d/llm/argo_brain/data_raw
├── config/                 # Text config such as windows_username.txt
└── README.md
```

## Setup (WSL Ubuntu)

1. **Create a Python virtual environment**

   ```bash
   cd /home/llm-argo/argo_brain
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Review `argo.toml` configuration**

   The repository ships with an `argo.toml` file at the project root. It controls storage paths, model endpoints, and vector-store settings:

   ```toml
   [data]
   root = "/mnt/d/llm/argo_brain"
   state_dir = "/mnt/d/llm/argo_brain/state"
   data_raw_path = "/mnt/d/llm/argo_brain/data_raw"
   models_root = "/mnt/d/llm/models"

   [vector_store]
   backend = "chroma"
   path = "/mnt/d/llm/argo_brain/vectordb"

   [llm]
   base_url = "http://127.0.0.1:8080/v1/chat/completions"
   model = "local-llm"
   ```

   Adjust paths as needed for your machine (or override via `ARGO_*` environment variables) before running any scripts.

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the Windows username**

   Either export `WINDOWS_USERNAME` before running the history ingest script:

   ```bash
   export WINDOWS_USERNAME="YourWindowsUser"
   ```

   or create `/home/llm-argo/argo_brain/config/windows_username.txt` with a single line containing the username that appears under `C:\Users\`.

5. **Start `llama-server` (example)**

   ```bash
   cd /home/llm-argo/llama.cpp
   ./llama-server \
     -m /mnt/d/llm/models/Qwen3-32B/qwen3-32b-q5_k_m.gguf \
     -c 4096 \
     -ngl 64 \
     -t 18 \
     --port 8080 \
     --host 0.0.0.0
   ```

   - `-m` points to the GGUF model file stored on `/mnt/d`.
   - `-c` sets context length.
   - `-ngl` controls GPU layers (tune for the RTX 5090).
   - `-t` sets CPU threads (Ryzen 9 has plenty of cores).
   - `--port/--host` expose an OpenAI-compatible API at `http://127.0.0.1:8080/v1/chat/completions`.
   - Running from `/home/llm-argo/llama.cpp` keeps the llama.cpp binaries in the WSL home directory while models remain on the large `/mnt/d` drive.

## Usage

All commands run from `/home/llm-argo/argo_brain`. Scripts live in `scripts/`.

### Chat with layered memory

Bring up the interactive CLI to create or resume sessions backed by the new memory stack:

```bash
python3 scripts/chat_cli.py            # random session ID
python3 scripts/chat_cli.py --session mysession123
python3 scripts/chat_cli.py --mode research --session deepdive1
```

Inside the REPL you can type natural language or one of the helper commands:

| Command     | Description                                           |
|-------------|-------------------------------------------------------|
| `:new`      | Start a brand-new session (fresh short-term buffer)   |
| `:facts`    | List stored profile facts from `profile_facts`        |
| `:summary`  | Show the rolling session summary                      |
| `:webcache` | Show the latest logged tool/browse runs               |
| `:stats`    | Show aggregated session statistics (tool usage, message counts) |
| `:tools`    | List available tools (e.g., web access, search)       |
| `:tool`     | Run a tool: `:tool <name> <query_or_url>`             |
| `:help`     | Show help                                             |
| `:quit`     | Exit the REPL                                         |

`--mode` switches the assistant's behavior and ingestion policy for the entire session:

- `quick_lookup` – default, caches live web results but stores only tiny summaries and nudges the LLM toward concise answers.
- **`research`** – **Enhanced deep research mode with planning-first architecture:**
  - Requires explicit research plan before tool execution
  - Multi-phase framework: Planning → Execution → Synthesis
  - Self-reflection prompts after each tool call
  - Real-time stopping conditions checklist
  - Source quality evaluation and citation requirements
  - Confidence assessment and knowledge gap identification
  - See [RESEARCH_MODE.md](RESEARCH_MODE.md) for details
- `ingest` – treats every provided document/URL as archival, stores full chunks + summaries, and primes the LLM to help with long-form archiving.

### Ingestion & RAG CLIs

- **Ingest a single URL**

  ```bash
  python3 scripts/rag_core.py https://example.com/article
  ```

- **Ingest a YouTube transcript**

  ```bash
  python3 scripts/youtube_ingest.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
  ```

- **Process the latest Chrome history**

  ```bash
  python3 scripts/history_ingest.py
  ```

  The script copies the locked Windows Chrome history DB from
  `/mnt/c/Users/<WINDOWS_USERNAME>/AppData/Local/Google/Chrome/User Data/Default/History`
  into `/mnt/d/llm/argo_brain/data_raw/chrome_history_copy`, queries only entries newer than the last recorded timestamp in `/mnt/d/llm/argo_brain/data_raw/history_state.json`, and ingests each URL. YouTube URLs are delegated to the transcript ingestor automatically.

- **Ask a question using RAG**

  ```bash
  python3 scripts/rag_core.py "What did I read about reinforcement learning yesterday?"
  ```

### Session modes & ingestion policy

A centralized `IngestionManager` now controls how fetched documents become long-term memory:

- Inputs arrive as normalized `SourceDocument` objects from tools/scripts.
- Policies determine retention: `EPHEMERAL` (web cache only), `SUMMARY_ONLY`, or `FULL`.
- Policy selection considers the current `SessionMode` (quick lookup, research, ingest), explicit user intent (e.g., manual memory writes), document type, and length.
- Chunks route into dedicated namespaces (`web_articles`, `youtube`, `notes`, `web_cache`) so retrieval filters stay simple and retention policies can evolve independently.

This layering lets quick fact-finding avoid polluting autobiographical memory while explicitly-ingested research dumps keep both the granular chunks and auto-generated summaries for later recall.

## Memory architecture

Argo Assistant builds prompts by fusing several memory sources:

1. **Short-term buffer** – The last *K* (default 6) user/assistant turns live in SQLite `messages` and are injected verbatim.
2. **Session summary** – Every *N* messages (default 20) Argo asks the LLM to compress older context and stores it in `session_summaries`.
3. **Autobiographical memory** – A distinct Chroma collection (`argo_autobiographical_memory`) stores long-lived facts extracted by a “memory writer” prompt. Metadata tracks `session_id`, `type`, and `source_type`.
4. **Profile facts table** – Structured snippets (preferences, ongoing projects, etc.) are stored in SQLite `profile_facts` for quick listing or soft-deactivation.
5. **Session summary snapshots** – In addition to the rolling summary, periodic snapshots are archived in SQLite so long-running sessions keep a hierarchical summary trail.
6. **Tool results** – Structured outputs from registered tools (e.g., live web access) are kept as first-class context items so prompts can cite them explicitly before they are persisted anywhere.
7. **Web cache** – Live browsing/tool outputs can be summarized into a dedicated collection (`argo_web_cache`) with provenance metadata (`source_type="live_web"`, `url`, `fetched_at`, `session_id`) so the assistant can re-use recent lookups without polluting autobiographical memory.
8. **Archival RAG store** – Existing ingestion pipelines populate the `CONFIG.collections.rag` namespace (defaults to `argo_web_articles`) with articles/YouTube/history. `argo_brain.rag.retrieve_knowledge()` provides relevant chunks.

Under the hood the vector store is accessed through a small interface defined in `argo_brain.vector_store`. The default backend is Chroma (embedded, local-first), but the adapter keeps each namespace (`autobiographical`, `web_cache`, `argo_web_articles`, etc.) isolated so you can swap in LanceDB or Qdrant later without rewriting ingestion code.

On each turn Argo:

1. Retrieves context from all layers (`MemoryManager.get_context_for_prompt`).
2. Builds a multi-part prompt (`ArgoAssistant.build_prompt`) containing system behavior, summary/memory snippets, recent conversation, and the new user message.
3. Calls `llama-server` through the OpenAI-compatible HTTP API.
4. Writes the new messages to SQLite, updates the running summary if due, and runs the memory-writer prompt to persist any durable facts to both SQLite and the autobiographical Chroma collection.

All prompt text lives in `argo_brain/memory/prompts.py` if you want to tweak tone or extraction heuristics.

## Tool system

Argo's assistant can now automatically call external tools when needed (the LLM emits a JSON tool request when it wants one). Tools follow a lightweight interface defined in `argo_brain.tools.base` (`Tool`, `ToolRequest`, `ToolResult`) and register with the assistant at startup. The default CLI wires in:

- **`WebSearchTool`** – search the web using DuckDuckGo (or SearXNG). Returns URLs and text snippets. Tracks search queries for iterative refinement in research mode.
- **`WebAccessTool`** – fetch a live web page, extract content with trafilatura, log the invocation (`tool_runs`), and cache the extracted text in `argo_web_cache`. Enforces URL scheme restrictions and host allow-lists for security.
- **`MemoryQueryTool`** – retrieve relevant personal knowledge base snippets via the vector store abstraction. Optional `namespace`, `source_type`, and `filters` inputs scope the search to specific collections.
- **`MemoryWriteTool`** – store summarized knowledge back into the personal vector store for future retrieval. Supports both `ephemeral` (auto-expires) and archival storage.

Additional tools can be added by implementing the `Tool` protocol and passing them to `ArgoAssistant`.

### Tool execution flow

When a tool is invoked (either automatically or manually via `:tool`):

1. The CLI (`:tool <name> <query>`) or automatic planner creates a `ToolRequest`.
2. The tool returns a `ToolResult`, which is surfaced in the next prompt under "Recent tool outputs".
3. `ToolTracker.process_result()` logs the run to SQLite and application logs with structured metrics.
4. Web content is automatically cached in the ephemeral `web_cache` namespace.

### Observability

Tool execution is now fully tracked for debugging and optimization:

- **Database audit log**: All tool invocations logged to SQLite `tool_runs` table
- **Structured application logging**: JSON-formatted logs with tool_name, session_id, input_length, output_length, snippet_count, metadata_keys
- **Error classification**: All tool failures logged with error_type and error_message
- **Session statistics**: Use `:stats` command to see aggregated tool usage breakdown

This keeps tool outputs inspectable (`:webcache`, `:stats`) and separates temporary tool context from the user's longer-term memory. The LLM can make up to 10 tool calls per turn in research mode (3 in quick-lookup mode) until it has enough information to answer.

## Testing

Unit tests live under `tests/` inside the project root and rely on environment overrides so they never write to `/mnt/d`. Activate your virtualenv and run:

```bash
cd /home/llm-argo/argo_brain
source ~/venvs/llm-wsl/bin/activate
ARGO_ROOT=$PWD/.tmpdata \
ARGO_STATE_DIR=$PWD/.tmpdata/state \
ARGO_DATA_RAW_PATH=$PWD/.tmpdata/data_raw \
ARGO_VECTOR_STORE_PATH=$PWD/.tmpdata/vectordb \
python3 -m unittest tests.test_ingestion tests.test_memory_query_tool
```

The overrides keep temporary SQLite/vector-store directories inside the workspace so the tests can run without elevated permissions or a mounted `/mnt/d`.

## Data locations & initialization

- **Vector DB** – Configured via `argo_brain.config.CONFIG`. Defaults to `/mnt/d/llm/argo_brain/vectordb`. Created automatically by Chroma on first write and houses multiple collections (`argo_web_articles`, `argo_autobiographical_memory`, `argo_web_cache`).
- **Autobiographical collection** – Stored alongside the RAG DB under the name `argo_autobiographical_memory`.
- **SQLite state** – Default path `/mnt/d/llm/argo_brain/state/argo_memory.sqlite3`. The schema is created automatically when `MemoryDB` is instantiated and now includes `tool_runs` (tool audit log) and `session_summary_snapshots` in addition to `messages`, `session_summaries`, and `profile_facts`.
- **Raw Chrome data** – `/mnt/d/llm/argo_brain/data_raw`. The history ingest script handles copying/locking.

You can customize any of these paths via environment variables (`ARGO_STORAGE_ROOT`, `ARGO_VECTOR_DB_PATH`, `ARGO_SQLITE_PATH`, etc.) before launching the scripts.

## How the archival RAG loop works

1. **Ingest** – Scripts fetch content (web article, YouTube transcript, or Chrome history URL) and clean the text with `trafilatura`.
2. **Embed** – Text chunks are embedded via `sentence-transformers` (`BAAI/bge-m3`).
3. **Store** – Embeddings, text, and metadata are upserted into a persistent Chroma DB at `/mnt/d/llm/argo_brain/vectordb`.
4. **Retrieve** – When a question is asked, Chroma returns the most similar chunks.
5. **LLM answer** – Retrieved context is passed to the local llama-server endpoint, which produces a grounded answer citing the chunks it used.

## WSL-specific notes

- Windows drives mount under `/mnt/c` and `/mnt/d`; ensure your Ubuntu user can read the Chrome profile at `/mnt/c/Users/<username>/`.
- Keep the vector DB and raw data on `/mnt/d` to take advantage of the large D: drive dedicated to LLM projects.
- Chrome must be closed or the copy operation may fail; rerun the history ingestion after Chrome exits if that happens.

## Troubleshooting

- If `sentence-transformers` downloads models slowly, manually download them to `/mnt/d` and point the `HF_HOME` env var there.
- If llama-server refuses connections, verify it is bound to `127.0.0.1:8080` and that you provided an `Authorization` header (any token works).

## Requirements

Python dependencies are listed in `requirements.txt`. Install them via:

```bash
pip install -r requirements.txt
```

Additional system requirements:

- Python 3.10+ inside WSL2 Ubuntu.
- llama.cpp / `llama-server` running locally (see Setup).
- Access to `/mnt/c` Chrome profile and `/mnt/d` storage for the DB/state directories.
