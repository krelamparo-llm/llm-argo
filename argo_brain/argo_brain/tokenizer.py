"""Tokenizer integration for chat template processing.

This module provides support for using HuggingFace transformers tokenizers
to apply model-specific chat templates, following best practices from
Qwen3-Coder-30B and other modern LLMs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging


class TokenizerWrapper:
    """Wrapper around HuggingFace tokenizer for chat template processing.

    This class provides a lightweight interface to tokenizer functionality
    without requiring the full transformers library in production.
    """

    def __init__(self, tokenizer_path: Optional[str] = None) -> None:
        """Initialize tokenizer wrapper.

        Args:
            tokenizer_path: Path to tokenizer directory or model name
        """
        self.logger = logging.getLogger("argo_brain.tokenizer")
        self.tokenizer_path = tokenizer_path
        self._tokenizer = None
        self._chat_template = None

        if tokenizer_path:
            self._load_tokenizer(tokenizer_path)

    def _load_tokenizer(self, path: str) -> None:
        """Load tokenizer from path.

        Args:
            path: Directory containing tokenizer files
        """
        try:
            # Try to import transformers
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(path)
            self.logger.info(f"Loaded tokenizer from {path}")

            # Extract chat template if available
            if hasattr(self._tokenizer, "chat_template"):
                self._chat_template = self._tokenizer.chat_template
                self.logger.info("Chat template loaded from tokenizer")

        except ImportError:
            self.logger.warning(
                "transformers library not available, tokenizer features disabled"
            )
        except Exception as exc:
            self.logger.error(f"Failed to load tokenizer from {path}: {exc}")

    def apply_chat_template(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        add_generation_prompt: bool = True,
        tokenize: bool = False,
    ) -> str:
        """Apply chat template to format messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            add_generation_prompt: Whether to add assistant prompt
            tokenize: Whether to return token IDs (not supported yet)

        Returns:
            Formatted prompt string
        """
        if not self._tokenizer:
            # Fallback: simple concatenation
            return self._simple_format(messages)

        try:
            return self._tokenizer.apply_chat_template(
                messages,
                tools=tools,
                add_generation_prompt=add_generation_prompt,
                tokenize=tokenize,
            )
        except Exception as exc:
            self.logger.error(f"Error applying chat template: {exc}")
            return self._simple_format(messages)

    def _simple_format(self, messages: List[Dict[str, str]]) -> str:
        """Simple fallback formatting without tokenizer.

        Args:
            messages: List of message dicts

        Returns:
            Concatenated string
        """
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        lines.append("<|im_start|>assistant\n")
        return "\n".join(lines)

    def encode(self, text: str) -> List[int]:
        """Encode text to token IDs.

        Args:
            text: Text to encode

        Returns:
            List of token IDs
        """
        if not self._tokenizer:
            self.logger.warning("Tokenizer not loaded, cannot encode")
            return []

        return self._tokenizer.encode(text)

    def decode(self, token_ids: List[int], skip_special_tokens: bool = True) -> str:
        """Decode token IDs to text.

        Args:
            token_ids: List of token IDs
            skip_special_tokens: Whether to skip special tokens

        Returns:
            Decoded text
        """
        if not self._tokenizer:
            self.logger.warning("Tokenizer not loaded, cannot decode")
            return ""

        return self._tokenizer.decode(token_ids, skip_special_tokens=skip_special_tokens)

    def load_chat_template_from_file(self, template_path: str) -> None:
        """Load chat template from a Jinja2 file.

        Args:
            template_path: Path to .jinja template file
        """
        try:
            path = Path(template_path)
            if not path.exists():
                self.logger.error(f"Template file not found: {template_path}")
                return

            with path.open("r", encoding="utf-8") as f:
                self._chat_template = f.read()

            self.logger.info(f"Loaded chat template from {template_path}")

        except Exception as exc:
            self.logger.error(f"Failed to load template from {template_path}: {exc}")

    def get_special_tokens(self) -> Dict[str, Any]:
        """Get special tokens configuration.

        Returns:
            Dictionary of special tokens
        """
        if not self._tokenizer:
            return {}

        return {
            "bos_token": getattr(self._tokenizer, "bos_token", None),
            "eos_token": getattr(self._tokenizer, "eos_token", None),
            "pad_token": getattr(self._tokenizer, "pad_token", None),
            "unk_token": getattr(self._tokenizer, "unk_token", None),
        }

    def format_tools_for_template(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format tools for chat template compatibility.

        Converts Argo tool definitions to OpenAI-compatible format.

        Args:
            tools: List of Argo tool definitions

        Returns:
            List of OpenAI-compatible tool definitions
        """
        formatted_tools = []

        for tool in tools:
            formatted = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            formatted_tools.append(formatted)

        return formatted_tools

    @property
    def is_loaded(self) -> bool:
        """Check if tokenizer is loaded."""
        return self._tokenizer is not None

    @property
    def vocab_size(self) -> int:
        """Get vocabulary size."""
        if not self._tokenizer:
            return 0
        return len(self._tokenizer)


def create_tokenizer(model_path: Optional[str] = None) -> TokenizerWrapper:
    """Factory function to create tokenizer wrapper.

    Args:
        model_path: Path to model directory containing tokenizer files

    Returns:
        TokenizerWrapper instance
    """
    return TokenizerWrapper(model_path)
