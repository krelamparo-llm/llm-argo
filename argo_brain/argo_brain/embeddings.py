"""Sentence-transformers embedding helpers for Argo Brain."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List, Sequence

from sentence_transformers import SentenceTransformer

from .config import CONFIG


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Return a cached embedding model instance."""

    return SentenceTransformer(CONFIG.embed_model)


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """Embed a collection of texts as dense vectors."""

    cleaned = [text.strip() for text in texts if text and text.strip()]
    if not cleaned:
        return []
    model = _get_model()
    embeddings = model.encode(cleaned, batch_size=8, normalize_embeddings=True)
    return [vec.tolist() if hasattr(vec, "tolist") else list(vec) for vec in embeddings]


def embed_single(text: str) -> List[float]:
    """Embed a single string and return one vector."""

    vectors = embed_texts([text])
    return vectors[0] if vectors else []
