"""Central configuration constants for Argo Brain."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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

# Collection names (aligned with main.txt spec)
DEFAULT_AUTOBIO_COLLECTION = os.environ.get(
    "ARGO_AUTOBIO_COLLECTION", "argo_autobiographical_memory"
)
DEFAULT_WEB_CACHE_COLLECTION = os.environ.get(
    "ARGO_WEB_CACHE_COLLECTION", "argo_web_cache"
)
# Renamed to match main.txt: reading_history
DEFAULT_READING_HISTORY_COLLECTION = os.environ.get(
    "ARGO_READING_HISTORY_COLLECTION", "argo_reading_history"
)
# Renamed to match main.txt: youtube_history
DEFAULT_YOUTUBE_HISTORY_COLLECTION = os.environ.get(
    "ARGO_YOUTUBE_HISTORY_COLLECTION", "argo_youtube_history"
)
# Renamed to match main.txt: notes_journal
DEFAULT_NOTES_JOURNAL_COLLECTION = os.environ.get(
    "ARGO_NOTES_JOURNAL_COLLECTION", "argo_notes_journal"
)

# Backward compatibility - OLD names (deprecated)
DEFAULT_WEB_ARTICLE_COLLECTION = os.environ.get(
    "ARGO_WEB_ARTICLE_COLLECTION", DEFAULT_READING_HISTORY_COLLECTION
)
DEFAULT_RAG_COLLECTION = os.environ.get(
    "ARGO_RAG_COLLECTION",
    DEFAULT_READING_HISTORY_COLLECTION,
)
DEFAULT_YOUTUBE_COLLECTION = os.environ.get(
    "ARGO_YOUTUBE_COLLECTION", DEFAULT_YOUTUBE_HISTORY_COLLECTION
)
DEFAULT_NOTES_COLLECTION = os.environ.get(
    "ARGO_NOTES_COLLECTION", DEFAULT_NOTES_JOURNAL_COLLECTION
)
DEFAULT_EMBED_MODEL = os.environ.get("ARGO_EMBED_MODEL", "BAAI/bge-m3")
DEFAULT_LLAMA_URL = _get_llm_setting("base_url", "http://127.0.0.1:8080/v1/chat/completions")
DEFAULT_LLAMA_MODEL = _get_llm_setting("model", "local-llm")


def _security_phrases_default() -> tuple[str, ...]:
    base = [
        "ignore previous instructions",
        "override the system prompt",
        "you are now",
        "forget all prior",
        "begin system override",
    ]
    return _get_security_list_setting("suspicious_phrases", base)


def _security_scheme_default() -> tuple[str, ...]:
    return _get_security_list_setting("web_allowed_schemes", ["http", "https"])


def _security_host_default() -> tuple[str, ...]:
    return _get_security_list_setting("web_allowed_hosts", [])


def _get_security_list_setting(name: str, default: list[str]) -> tuple[str, ...]:
    env_key = f"ARGO_SECURITY_{name.upper()}"
    if env_key in os.environ:
        raw = os.environ[env_key]
    else:
        security_section = _CONFIG_DATA.get("security", {})
        raw = security_section.get(name)
    if raw is None:
        return tuple(default)
    if isinstance(raw, str):
        items = [item.strip() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(item).strip() for item in raw if str(item).strip()]
    else:
        return tuple(default)
    return tuple(items) if items else tuple(default)


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
    """Configuration for llama-server interactions.

    Best practices from Qwen3-Coder-30B:
    - temperature: 0.7 for balanced creativity/accuracy
    - top_p: 0.8 for nucleus sampling
    - top_k: 20 for limited vocabulary
    - repetition_penalty: 1.05 to reduce repetition
    - max_tokens: 65536 for comprehensive responses
    """

    base_url: str = DEFAULT_LLAMA_URL
    model: str = DEFAULT_LLAMA_MODEL
    temperature: float = float(os.environ.get("ARGO_LLM_TEMPERATURE", 0.7))
    max_tokens: int = int(os.environ.get("ARGO_LLM_MAX_TOKENS", 2048))
    request_timeout: int = int(os.environ.get("ARGO_LLM_TIMEOUT", 180))

    # Advanced sampling parameters (Qwen3-Coder best practices)
    top_p: float = float(os.environ.get("ARGO_LLM_TOP_P", 0.8))
    top_k: int = int(os.environ.get("ARGO_LLM_TOP_K", 20))
    repetition_penalty: float = float(os.environ.get("ARGO_LLM_REPETITION_PENALTY", 1.05))

    # Model-specific settings
    use_chat_template: bool = bool(int(os.environ.get("ARGO_LLM_USE_CHAT_TEMPLATE", "0")))
    tokenizer_path: Optional[str] = os.environ.get("ARGO_LLM_TOKENIZER_PATH")


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
class RetentionPolicy:
    """Defines retention rules for a namespace."""

    ttl_days: int | None = None  # None = keep forever
    enable_decay: bool = True
    decay_half_life_days: int = 90  # Score halves every N days
    max_age_days: int | None = None  # Hard cutoff (not currently used)


@dataclass(frozen=True)
class Collections:
    """Chroma collection names (aligned with main.txt specification)."""

    # New canonical names (match main.txt)
    reading_history: str = DEFAULT_READING_HISTORY_COLLECTION
    youtube_history: str = DEFAULT_YOUTUBE_HISTORY_COLLECTION
    notes_journal: str = DEFAULT_NOTES_JOURNAL_COLLECTION
    autobiographical_memory: str = DEFAULT_AUTOBIO_COLLECTION
    web_cache: str = DEFAULT_WEB_CACHE_COLLECTION

    # Backward compatibility aliases (DEPRECATED - use new names)
    rag: str = DEFAULT_RAG_COLLECTION  # Alias for reading_history
    web_articles: str = DEFAULT_WEB_ARTICLE_COLLECTION  # OLD name
    youtube: str = DEFAULT_YOUTUBE_COLLECTION  # OLD name
    notes: str = DEFAULT_NOTES_COLLECTION  # OLD name
    autobiographical: str = DEFAULT_AUTOBIO_COLLECTION  # OLD name

    # Retention policies per namespace
    _policies: Dict[str, RetentionPolicy] = field(default_factory=lambda: {
        "argo_reading_history": RetentionPolicy(
            ttl_days=None,  # Keep forever
            enable_decay=True,
            decay_half_life_days=180,  # 6 months
        ),
        "argo_youtube_history": RetentionPolicy(
            ttl_days=None,
            enable_decay=True,
            decay_half_life_days=180,
        ),
        "argo_notes_journal": RetentionPolicy(
            ttl_days=None,  # High-trust notes never expire
            enable_decay=False,  # Always full weight
        ),
        "argo_autobiographical_memory": RetentionPolicy(
            ttl_days=None,
            enable_decay=False,  # Personal facts always relevant
        ),
        "argo_web_cache": RetentionPolicy(
            ttl_days=7,  # Ephemeral - 1 week
            enable_decay=True,
            decay_half_life_days=3,  # Decay fast
        ),
    })

    def get_policy(self, namespace: str) -> RetentionPolicy:
        """Get retention policy for namespace."""
        return self._policies.get(namespace, RetentionPolicy())


@dataclass(frozen=True)
class VectorStoreConfig:
    """Vector store backend settings."""

    backend: str = _get_vector_store_setting("backend", "chroma")
    path: Path = VECTOR_DB_PATH


@dataclass(frozen=True)
class SecurityConfig:
    """Application-layer security controls."""

    context_max_chunks: int = int(os.environ.get("ARGO_SECURITY_CONTEXT_MAX_CHUNKS", 8))
    context_char_budget: int = int(os.environ.get("ARGO_SECURITY_CONTEXT_CHAR_BUDGET", 6000))
    enable_injection_filter: bool = bool(int(os.environ.get("ARGO_SECURITY_ENABLE_INJECTION_FILTER", "1")))
    suspicious_phrases: tuple[str, ...] = field(default_factory=_security_phrases_default)
    web_allowed_schemes: tuple[str, ...] = field(default_factory=_security_scheme_default)
    web_allowed_hosts: tuple[str, ...] = field(default_factory=_security_host_default)


@dataclass(frozen=True)
class AppConfig:
    """Aggregate configuration for the Argo Brain runtime."""

    paths: Paths = Paths()
    collections: Collections = Collections()
    memory: MemoryConfig = MemoryConfig()
    llm: LLMConfig = LLMConfig()
    embed_model: str = DEFAULT_EMBED_MODEL
    vector_store: VectorStoreConfig = VectorStoreConfig()
    security: SecurityConfig = SecurityConfig()


CONFIG: Final[AppConfig] = AppConfig()

# Ensure important directories exist at import time.
for required_path in [
    CONFIG.paths.data_root,
    CONFIG.paths.state_dir,
    CONFIG.paths.vector_db_path,
    CONFIG.paths.data_raw_path,
]:
    required_path.mkdir(parents=True, exist_ok=True)
