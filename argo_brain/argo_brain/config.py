"""Central configuration constants for Argo Brain."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Final

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.10
    import tomli as tomllib

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = Path(os.environ.get("ARGO_CONFIG_FILE", PROJECT_ROOT / "argo.toml"))


def _load_config_data() -> Dict[str, Any]:
    if DEFAULT_CONFIG_PATH.exists():
        with DEFAULT_CONFIG_PATH.open("rb") as fh:
            return tomllib.load(fh)
    return {}


_CONFIG_DATA = _load_config_data()


def _get_data_setting(name: str, default: str) -> str:
    env_key = f"ARGO_{name.upper()}"
    if env_key in os.environ:
        return os.environ[env_key]
    data_section = _CONFIG_DATA.get("data", {})
    return str(data_section.get(name, default))


def _get_vector_store_setting(name: str, default: str) -> str:
    env_key = f"ARGO_VECTOR_STORE_{name.upper()}"
    if env_key in os.environ:
        return os.environ[env_key]
    section = _CONFIG_DATA.get("vector_store", {})
    return str(section.get(name, default))


def _get_llm_setting(name: str, default: str) -> str:
    env_key = f"ARGO_LLM_{name.upper()}"
    if env_key in os.environ:
        return os.environ[env_key]
    section = _CONFIG_DATA.get("llm", {})
    return str(section.get(name, default))


DATA_ROOT = Path(_get_data_setting("root", "/mnt/d/llm/argo_brain"))
STATE_DIR = Path(_get_data_setting("state_dir", str(DATA_ROOT / "state")))
VECTOR_DB_PATH = Path(_get_vector_store_setting("path", str(DATA_ROOT / "vectordb")))
DATA_RAW_PATH = Path(_get_data_setting("data_raw_path", str(DATA_ROOT / "data_raw")))
MODELS_ROOT = Path(_get_data_setting("models_root", "/mnt/d/llm/models"))
SQLITE_PATH = Path(
    os.environ.get("ARGO_SQLITE_PATH", STATE_DIR / "argo_memory.sqlite3")
)

DEFAULT_AUTOBIO_COLLECTION = os.environ.get(
    "ARGO_AUTOBIO_COLLECTION", "argo_autobiographical_memory"
)
DEFAULT_WEB_CACHE_COLLECTION = os.environ.get(
    "ARGO_WEB_CACHE_COLLECTION", "argo_web_cache"
)
DEFAULT_WEB_ARTICLE_COLLECTION = os.environ.get(
    "ARGO_WEB_ARTICLE_COLLECTION", "argo_web_articles"
)
DEFAULT_RAG_COLLECTION = os.environ.get(
    "ARGO_RAG_COLLECTION",
    DEFAULT_WEB_ARTICLE_COLLECTION,
)
DEFAULT_YOUTUBE_COLLECTION = os.environ.get("ARGO_YOUTUBE_COLLECTION", "argo_youtube")
DEFAULT_NOTES_COLLECTION = os.environ.get("ARGO_NOTES_COLLECTION", "argo_notes")
DEFAULT_EMBED_MODEL = os.environ.get("ARGO_EMBED_MODEL", "BAAI/bge-m3")
DEFAULT_LLAMA_URL = _get_llm_setting("base_url", "http://127.0.0.1:8080/v1/chat/completions")
DEFAULT_LLAMA_MODEL = _get_llm_setting("model", "local-llm")


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

    project_root: Path = PROJECT_ROOT
    data_root: Path = DATA_ROOT
    state_dir: Path = STATE_DIR
    vector_db_path: Path = VECTOR_DB_PATH
    data_raw_path: Path = DATA_RAW_PATH
    models_root: Path = MODELS_ROOT
    sqlite_path: Path = SQLITE_PATH
    config_file: Path = DEFAULT_CONFIG_PATH


@dataclass(frozen=True)
class Collections:
    """Chroma collection names."""

    rag: str = DEFAULT_RAG_COLLECTION
    autobiographical: str = DEFAULT_AUTOBIO_COLLECTION
    web_cache: str = DEFAULT_WEB_CACHE_COLLECTION
    web_articles: str = DEFAULT_WEB_ARTICLE_COLLECTION
    youtube: str = DEFAULT_YOUTUBE_COLLECTION
    notes: str = DEFAULT_NOTES_COLLECTION


@dataclass(frozen=True)
class VectorStoreConfig:
    """Vector store backend settings."""

    backend: str = _get_vector_store_setting("backend", "chroma")
    path: Path = VECTOR_DB_PATH


@dataclass(frozen=True)
class AppConfig:
    """Aggregate configuration for the Argo Brain runtime."""

    paths: Paths = Paths()
    collections: Collections = Collections()
    memory: MemoryConfig = MemoryConfig()
    llm: LLMConfig = LLMConfig()
    embed_model: str = DEFAULT_EMBED_MODEL
    vector_store: VectorStoreConfig = VectorStoreConfig()


CONFIG: Final[AppConfig] = AppConfig()

# Ensure important directories exist at import time.
for required_path in [
    CONFIG.paths.data_root,
    CONFIG.paths.state_dir,
    CONFIG.paths.vector_db_path,
    CONFIG.paths.data_raw_path,
]:
    required_path.mkdir(parents=True, exist_ok=True)
