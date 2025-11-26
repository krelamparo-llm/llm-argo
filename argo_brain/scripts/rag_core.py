"""Thin CLI entry point for the refactored RAG module."""

from __future__ import annotations

import sys
from typing import List

from argo_brain.llm_client import LLMClient
from argo_brain.rag import answer_question, ingest_url


def _looks_like_url(text: str) -> bool:
    lowered = text.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _main(argv: List[str]) -> None:
    if len(argv) < 2:
        print(
            "Usage: python3 rag_core.py <url|question>\n"
            " - Provide an http(s) URL to ingest it.\n"
            " - Provide a natural language question for a RAG answer."
        )
        return
    query = " ".join(argv[1:]).strip()
    if _looks_like_url(query):
        ingest_url(query)
        print(f"Ingested URL: {query}")
    else:
        client = LLMClient()
        print(answer_question(query, llm_client=client))


if __name__ == "__main__":
    _main(sys.argv)
