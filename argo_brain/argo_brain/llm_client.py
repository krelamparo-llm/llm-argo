"""HTTP client for llama-server's OpenAI-compatible API."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import logging
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
        self.logger = logging.getLogger("argo_brain.llm_client")
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
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        repetition_penalty: Optional[float] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a chat completion request and return the assistant content.

        Args:
            messages: Chat messages to send
            temperature: Sampling temperature (default from config: 0.7)
            max_tokens: Maximum tokens to generate (default from config: 16384)
            top_p: Nucleus sampling probability (default from config: 0.8)
            top_k: Top-K sampling limit (default from config: 20)
            repetition_penalty: Penalty for repetition (default from config: 1.05)
            extra_payload: Additional parameters to send

        Returns:
            Assistant response text
        """

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "messages": [message.__dict__ for message in messages],
        }

        # Add advanced sampling parameters (Qwen3-Coder best practices)
        if top_p is not None:
            payload["top_p"] = top_p
        elif hasattr(self.config, "top_p"):
            payload["top_p"] = self.config.top_p

        if top_k is not None:
            payload["top_k"] = top_k
        elif hasattr(self.config, "top_k"):
            payload["top_k"] = self.config.top_k

        if repetition_penalty is not None:
            payload["repetition_penalty"] = repetition_penalty
        elif hasattr(self.config, "repetition_penalty"):
            payload["repetition_penalty"] = self.config.repetition_penalty

        if extra_payload:
            payload.update(extra_payload)

        start = time.perf_counter()
        try:
            response = self.session.post(
                self.config.base_url,
                data=json.dumps(payload),
                headers=self.headers,
                timeout=self.config.request_timeout,
            )
        except requests.exceptions.Timeout as exc:
            msg = (
                f"LLM request timed out after {self.config.request_timeout}s "
                f"(base_url={self.config.base_url}). "
                "Ensure llama-server is running and loaded, or raise ARGO_LLM_TIMEOUT."
            )
            self.logger.error(msg, exc_info=True)
            raise RuntimeError(msg) from exc
        except requests.exceptions.ConnectionError as exc:
            msg = (
                f"Could not connect to LLM server at {self.config.base_url}. "
                "Start llama-server or set ARGO_LLM_BASE_URL to the correct endpoint."
            )
            self.logger.error(msg, exc_info=True)
            raise RuntimeError(msg) from exc
        except requests.exceptions.RequestException as exc:
            msg = f"LLM request failed for {self.config.base_url}: {exc}"
            self.logger.error(msg, exc_info=True)
            raise RuntimeError(msg) from exc
        elapsed = time.perf_counter() - start

        if response.status_code != 200:
            self.logger.error(
                "LLM request failed",
                extra={
                    "status_code": response.status_code,
                    "elapsed_ms": round(elapsed * 1000, 2),
                }
            )
            raise RuntimeError(
                f"llama-server returned {response.status_code}: {response.text[:2000]}"
            )

        data = response.json()

        # Extract token usage from llama-server response
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # Log completion with token counts
        self.logger.info(
            "LLM request completed",
            extra={
                "status_code": response.status_code,
                "elapsed_ms": round(elapsed * 1000, 2),
                "tokens_max": payload.get("max_tokens"),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        )

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected LLM response: {data}") from exc
