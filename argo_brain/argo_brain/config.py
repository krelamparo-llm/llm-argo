"""Central configuration constants for Argo Brain."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

DEFAULT_STORAGE_ROOT = Path(os.environ.get("ARGO_STORAGE_ROOT", "/mnt/d/llm/argo_brain"))
DEFAULT_STATE_DIR = Path(os.environ.get("ARGO_STATE_DIR", DEFAULT_STORAGE_ROOT / "state"))
DEFAULT_VECTOR_DB_PATH = Path(
    os.environ.get("ARGO_VECTOR_DB_PATH", DEFAULT_STORAGE_ROOT / "vectordb")
)
DEFAULT_DATA_RAW_PATH = Path(
    os.environ.get("ARGO_DATA_RAW_PATH", DEFAULT_STORAGE_ROOT / "data_raw")
)
DEFAULT_SQLITE_PATH = Path(
    os.environ.get("ARGO_SQLITE_PATH", DEFAULT_STATE_DIR / "argo_memory.sqlite3")
)

DEFAULT_RAG_COLLECTION = os.environ.get("ARGO_RAG_COLLECTION", "argo_brain_memory")
DEFAULT_AUTOBIO_COLLECTION = os.environ.get(
    "ARGO_AUTOBIO_COLLECTION", "argo_autobiographical_memory"
)
DEFAULT_WEB_CACHE_COLLECTION = os.environ.get(
    "ARGO_WEB_CACHE_COLLECTION", "argo_web_cache"
)
DEFAULT_EMBED_MODEL = os.environ.get("ARGO_EMBED_MODEL", "BAAI/bge-m3")
DEFAULT_LLAMA_URL = os.environ.get(
    "LLAMA_SERVER_URL", "http://127.0.0.1:8080/v1/chat/completions"
)
DEFAULT_LLAMA_MODEL = os.environ.get("LLAMA_MODEL_NAME", "local-llm")


@dataclass(frozen=True)
class MemoryConfig:
    """Tunable parameters for the layered memory system."""

    short_term_window: int = int(os.environ.get("ARGO_SHORT_TERM_WINDOW", 6))
    summary_interval: int = int(os.environ.get("ARGO_SUMMARY_INTERVAL", 20))
    summary_history_limit: int = int(os.environ.get("ARGO_SUMMARY_HISTORY_LIMIT", 200))
    summary_snapshot_interval: int = int(os.environ.get("ARGO_SUMMARY_SNAPSHOT_INTERVAL", 80))
    autobiographical_k: int = int(os.environ.get("ARGO_AUTOBIO_K", 5))
    rag_k: int = int(os.environ.get("ARGO_RAG_K", 5))
    web_cache_ttl_days: int = int(os.environ.get("ARGO_WEB_CACHE_TTL_DAYS", 7))


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for llama-server interactions."""

    base_url: str = DEFAULT_LLAMA_URL
    model: str = DEFAULT_LLAMA_MODEL
    temperature: float = float(os.environ.get("ARGO_LLM_TEMPERATURE", 0.2))
    max_tokens: int = int(os.environ.get("ARGO_LLM_MAX_TOKENS", 512))
    request_timeout: int = int(os.environ.get("ARGO_LLM_TIMEOUT", 60))


@dataclass(frozen=True)
class Paths:
    """Filesystem paths used throughout the project."""

    storage_root: Path = DEFAULT_STORAGE_ROOT
    state_dir: Path = DEFAULT_STATE_DIR
    vector_db_path: Path = DEFAULT_VECTOR_DB_PATH
    data_raw_path: Path = DEFAULT_DATA_RAW_PATH
    sqlite_path: Path = DEFAULT_SQLITE_PATH


@dataclass(frozen=True)
class Collections:
    """Chroma collection names."""

    rag: str = DEFAULT_RAG_COLLECTION
    autobiographical: str = DEFAULT_AUTOBIO_COLLECTION
    web_cache: str = DEFAULT_WEB_CACHE_COLLECTION


@dataclass(frozen=True)
class AppConfig:
    """Aggregate configuration for the Argo Brain runtime."""

    paths: Paths = Paths()
    collections: Collections = Collections()
    memory: MemoryConfig = MemoryConfig()
    llm: LLMConfig = LLMConfig()
    embed_model: str = DEFAULT_EMBED_MODEL


CONFIG: Final[AppConfig] = AppConfig()

# Ensure important directories exist at import time.
CONFIG.paths.state_dir.mkdir(parents=True, exist_ok=True)
CONFIG.paths.vector_db_path.mkdir(parents=True, exist_ok=True)
