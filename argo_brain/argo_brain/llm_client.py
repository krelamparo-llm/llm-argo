"""HTTP client for llama-server's OpenAI-compatible API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests

from .config import CONFIG, LLMConfig


@dataclass
class ChatMessage:
    """Simple representation of an OpenAI-style chat message."""

    role: str
    content: str


class LLMClient:
    """Thin wrapper over llama-server's OpenAI-compatible endpoint."""

    def __init__(self, config: Optional[LLMConfig] = None, headers: Optional[Dict[str, str]] = None) -> None:
        self.config = config or CONFIG.llm
        self.session = requests.Session()
        default_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer local-token",
        }
        if headers:
            default_headers.update(headers)
        self.headers = default_headers

    def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a chat completion request and return the assistant content."""

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "messages": [message.__dict__ for message in messages],
        }
        if extra_payload:
            payload.update(extra_payload)

        response = self.session.post(
            self.config.base_url,
            data=json.dumps(payload),
            headers=self.headers,
            timeout=self.config.request_timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"llama-server returned {response.status_code}: {response.text[:2000]}"
            )
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected LLM response: {data}") from exc
