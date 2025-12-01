"""Application runtime bootstrap helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig, CONFIG
from .core.memory.ingestion import IngestionManager
from .core.vector_store.factory import create_vector_store
from .llm_client import LLMClient
from .memory.manager import MemoryManager


@dataclass
class AppRuntime:
    """Bundle of shared services for the Argo application."""

    config: AppConfig
    llm_client: LLMClient
    vector_store: any
    ingestion_manager: IngestionManager
    memory_manager: MemoryManager


def create_runtime(config: AppConfig = CONFIG) -> AppRuntime:
    """Instantiate shared services once and wire dependencies explicitly."""

    llm_client = LLMClient()
    vector_store = create_vector_store(config)
    ingestion_manager = IngestionManager(vector_store=vector_store, llm_client=llm_client)
    memory_manager = MemoryManager(
        llm_client=llm_client,
        vector_store=vector_store,
        ingestion_manager=ingestion_manager,
    )
    return AppRuntime(
        config=config,
        llm_client=llm_client,
        vector_store=vector_store,
        ingestion_manager=ingestion_manager,
        memory_manager=memory_manager,
    )


__all__ = ["AppRuntime", "create_runtime"]
