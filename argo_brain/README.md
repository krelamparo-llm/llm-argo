# Argo Brain

Argo Brain ingests your personal browsing data, web articles, and YouTube transcripts into a persistent Chroma vector database stored on `/mnt/d`. The scripts run inside WSL Ubuntu and talk to a local `llama-server` so you can ask grounded questions about everything you've read or watched.

## Project layout

```
/home/llm-argo/argo_brain/
├── scripts/        # Python modules and CLIs (rag_core, youtube_ingest, history_ingest)
├── vectordb/       # Source tree placeholder; actual DB stored on /mnt/d/llm/argo_brain/vectordb
├── data_raw/       # Placeholder; Chrome history copies actually live on /mnt/d/llm/argo_brain/data_raw
├── config/         # Text config such as windows_username.txt
└── README.md
```

## Setup (WSL Ubuntu)

1. **Create a Python virtual environment**

   ```bash
   cd /home/llm-argo/argo_brain
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**

   ```bash
   pip install chromadb sentence-transformers trafilatura youtube-transcript-api requests
   ```

3. **Configure the Windows username**

   Either export `WINDOWS_USERNAME` before running the history ingest script:

   ```bash
   export WINDOWS_USERNAME="YourWindowsUser"
   ```

   or create `/home/llm-argo/argo_brain/config/windows_username.txt` with a single line containing the username that appears under `C:\Users\`.

4. **Start `llama-server` (example)**

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

## How the RAG loop works

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
