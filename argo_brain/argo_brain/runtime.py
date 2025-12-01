"""Application runtime bootstrap helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig, CONFIG
from .core.memory.ingestion import IngestionManager
from .core.vector_store.factory import create_vector_store
from .llm_client import LLMClient
from .memory.db import MemoryDB
from .memory.manager import MemoryManager
from .memory.session_manager import SessionManager
from .memory.tool_tracker import ToolTracker


@dataclass
class AppRuntime:
    """Bundle of shared services for the Argo application."""

    config: AppConfig
    llm_client: LLMClient
    vector_store: any
    ingestion_manager: IngestionManager
    memory_db: MemoryDB
    session_manager: SessionManager
    tool_tracker: ToolTracker
    memory_manager: MemoryManager


def create_runtime(config: AppConfig = CONFIG) -> AppRuntime:
    """Instantiate shared services once and wire dependencies explicitly.

    Dependency order:
    1. Basic clients (LLM, vector store, DB)
    2. IngestionManager (needs vector store)
    3. SessionManager (needs DB, LLM)
    4. ToolTracker (needs DB, IngestionManager)
    5. MemoryManager (needs DB, LLM, SessionManager, vector store)
    """
    # Layer 1: Clients
    llm_client = LLMClient()
    vector_store = create_vector_store(config)
    memory_db = MemoryDB()

    # Layer 2: Ingestion
    ingestion_manager = IngestionManager(vector_store=vector_store)

    # Layer 3: Session and Tool tracking
    session_manager = SessionManager(db=memory_db, llm_client=llm_client)
    tool_tracker = ToolTracker(db=memory_db, ingestion_manager=ingestion_manager)

    # Layer 4: Memory management
    memory_manager = MemoryManager(
        db=memory_db,
        llm_client=llm_client,
        session_manager=session_manager,
        vector_store=vector_store,
    )

    return AppRuntime(
        config=config,
        llm_client=llm_client,
        vector_store=vector_store,
        ingestion_manager=ingestion_manager,
        memory_db=memory_db,
        session_manager=session_manager,
        tool_tracker=tool_tracker,
        memory_manager=memory_manager,
    )


__all__ = ["AppRuntime", "create_runtime"]
