"""Model Registry with auto-detection of model-specific configurations.

This module provides automatic discovery and loading of model-specific:
- Tokenizers (tokenizer.json, tokenizer_config.json)
- Chat templates (chat_template.jinja)
- Tool parsers (e.g., qwen3coder_tool_parser.py)
- Configuration files (config.json, generation_config.json)

Falls back to default implementations when model-specific files are not available.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging


@dataclass
class ModelConfig:
    """Container for model-specific configuration."""

    name: str
    path: Path
    has_tokenizer: bool = False
    has_chat_template: bool = False
    has_tool_parser: bool = False
    has_config: bool = False
    has_argo_prompts: bool = False  # NEW: Per-model prompt configuration

    # Loaded components
    tokenizer_config: Optional[Dict[str, Any]] = None
    chat_template: Optional[str] = None
    tool_parser_class: Optional[type] = None
    model_config: Optional[Dict[str, Any]] = None
    generation_config: Optional[Dict[str, Any]] = None
    argo_prompts: Optional[Any] = None  # NEW: ModelPromptConfig instance

    # Recommended settings
    recommended_temperature: Optional[float] = None
    recommended_top_p: Optional[float] = None
    recommended_top_k: Optional[int] = None
    recommended_repetition_penalty: Optional[float] = None
    recommended_max_tokens: Optional[int] = None


class ModelRegistry:
    """Registry for managing model-specific configurations with fallbacks.

    This class automatically detects and loads model-specific files from the
    models directory, providing a unified interface with sensible defaults.

    Example:
        >>> registry = ModelRegistry(models_root="/mnt/d/llm/models")
        >>> model = registry.get_model("qwen3-coder-30b")
        >>> if model.has_tokenizer:
        ...     tokenizer = registry.load_tokenizer(model)
    """

    def __init__(self, models_root: Optional[Path] = None) -> None:
        """Initialize the model registry.

        Args:
            models_root: Root directory containing model folders
        """
        self.logger = logging.getLogger("argo_brain.model_registry")
        self.models_root = Path(models_root) if models_root else None
        self._models: Dict[str, ModelConfig] = {}

        if self.models_root and self.models_root.exists():
            self._scan_models()

    def _scan_models(self) -> None:
        """Scan the models root directory for available models."""
        if not self.models_root or not self.models_root.exists():
            return

        self.logger.info(f"Scanning for models in {self.models_root}")

        for model_dir in self.models_root.iterdir():
            if not model_dir.is_dir():
                continue

            # Skip hidden directories and cache
            if model_dir.name.startswith("."):
                continue

            model_config = self._detect_model_config(model_dir)
            if model_config:
                self._models[model_dir.name] = model_config
                self.logger.info(
                    f"Detected model '{model_dir.name}': "
                    f"tokenizer={model_config.has_tokenizer}, "
                    f"template={model_config.has_chat_template}, "
                    f"parser={model_config.has_tool_parser}"
                )

    def _detect_model_config(self, model_dir: Path) -> Optional[ModelConfig]:
        """Detect what configuration files are available for a model.

        Args:
            model_dir: Path to model directory

        Returns:
            ModelConfig with detected capabilities
        """
        config = ModelConfig(name=model_dir.name, path=model_dir)

        # Check for tokenizer files
        tokenizer_files = [
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json"
        ]
        config.has_tokenizer = any((model_dir / f).exists() for f in tokenizer_files)

        # Check for chat template
        template_files = ["chat_template.jinja", "template.jinja"]
        for template_file in template_files:
            template_path = model_dir / template_file
            if template_path.exists():
                config.has_chat_template = True
                try:
                    config.chat_template = template_path.read_text(encoding="utf-8")
                except Exception as exc:
                    self.logger.warning(f"Failed to read chat template from {template_path}: {exc}")

        # Check for tool parser
        parser_candidates = list(model_dir.glob("*tool_parser.py"))
        if parser_candidates:
            config.has_tool_parser = True
            # Store the path for later dynamic loading
            config.tool_parser_path = parser_candidates[0]

        # Load config.json
        config_path = model_dir / "config.json"
        if config_path.exists():
            config.has_config = True
            try:
                with config_path.open("r", encoding="utf-8") as f:
                    config.model_config = json.load(f)
            except Exception as exc:
                self.logger.warning(f"Failed to load config.json from {config_path}: {exc}")

        # Load generation_config.json
        gen_config_path = model_dir / "generation_config.json"
        if gen_config_path.exists():
            try:
                with gen_config_path.open("r", encoding="utf-8") as f:
                    config.generation_config = json.load(f)
            except Exception as exc:
                self.logger.warning(f"Failed to load generation_config.json: {exc}")

        # Load tokenizer_config.json for additional settings
        tokenizer_config_path = model_dir / "tokenizer_config.json"
        if tokenizer_config_path.exists():
            try:
                with tokenizer_config_path.open("r", encoding="utf-8") as f:
                    config.tokenizer_config = json.load(f)
            except Exception as exc:
                self.logger.warning(f"Failed to load tokenizer_config.json: {exc}")

        # Extract recommended settings from README.md if present
        readme_path = model_dir / "README.md"
        if readme_path.exists():
            self._extract_recommendations_from_readme(readme_path, config)

        # NEW: Load argo_prompts.yaml or argo_prompts.json for per-model prompt config
        self._load_argo_prompts(model_dir, config)

        return config

    def _load_argo_prompts(self, model_dir: Path, config: ModelConfig) -> None:
        """Load Argo-specific prompt configuration if available.

        Checks for argo_prompts.yaml or argo_prompts.json in the model directory.
        If not found, attempts to infer configuration from model name.

        Args:
            model_dir: Path to model directory
            config: ModelConfig to update
        """
        from .model_prompts import load_prompt_config, infer_prompt_config

        # Try to load explicit configuration
        prompt_config = load_prompt_config(model_dir)

        if prompt_config:
            config.has_argo_prompts = True
            config.argo_prompts = prompt_config
            self.logger.info(
                f"Loaded argo_prompts for {config.name}: "
                f"format={prompt_config.tool_calling.format}, "
                f"thinking={prompt_config.thinking.enabled}"
            )
        else:
            # Infer from model name
            prompt_config = infer_prompt_config(config.name, model_dir)
            config.argo_prompts = prompt_config
            self.logger.debug(
                f"Inferred prompt config for {config.name}: "
                f"format={prompt_config.tool_calling.format}"
            )

    def _extract_recommendations_from_readme(
        self, readme_path: Path, config: ModelConfig
    ) -> None:
        """Extract recommended sampling parameters from README.

        Looks for patterns like:
        - temperature=0.7
        - top_p: 0.8
        - etc.

        Args:
            readme_path: Path to README.md
            config: ModelConfig to update
        """
        try:
            readme_text = readme_path.read_text(encoding="utf-8")

            # Look for parameter recommendations
            import re

            # Temperature
            temp_match = re.search(r"temperature[=:]\s*([0-9.]+)", readme_text, re.IGNORECASE)
            if temp_match:
                config.recommended_temperature = float(temp_match.group(1))

            # Top P
            top_p_match = re.search(r"top_p[=:]\s*([0-9.]+)", readme_text, re.IGNORECASE)
            if top_p_match:
                config.recommended_top_p = float(top_p_match.group(1))

            # Top K
            top_k_match = re.search(r"top_k[=:]\s*([0-9]+)", readme_text, re.IGNORECASE)
            if top_k_match:
                config.recommended_top_k = int(top_k_match.group(1))

            # Repetition penalty
            rep_match = re.search(
                r"repetition_penalty[=:]\s*([0-9.]+)", readme_text, re.IGNORECASE
            )
            if rep_match:
                config.recommended_repetition_penalty = float(rep_match.group(1))

            # Max tokens (look for various names)
            max_tokens_patterns = [
                r"max_tokens[=:]\s*([0-9,]+)",
                r"max_new_tokens[=:]\s*([0-9,]+)",
                r"output.*?([0-9,]+)\s*tokens"
            ]
            for pattern in max_tokens_patterns:
                match = re.search(pattern, readme_text, re.IGNORECASE)
                if match:
                    # Remove commas from number
                    token_str = match.group(1).replace(",", "")
                    config.recommended_max_tokens = int(token_str)
                    break

            if any([
                config.recommended_temperature,
                config.recommended_top_p,
                config.recommended_top_k,
                config.recommended_repetition_penalty,
                config.recommended_max_tokens
            ]):
                self.logger.info(
                    f"Extracted recommendations from README for {config.name}: "
                    f"temp={config.recommended_temperature}, "
                    f"top_p={config.recommended_top_p}, "
                    f"top_k={config.recommended_top_k}"
                )

        except Exception as exc:
            self.logger.debug(f"Could not extract recommendations from README: {exc}")

    def get_model(self, name: str) -> Optional[ModelConfig]:
        """Get model configuration by name.

        Args:
            name: Model name (folder name)

        Returns:
            ModelConfig or None if not found
        """
        return self._models.get(name)

    def list_models(self) -> List[str]:
        """Get list of available model names.

        Returns:
            List of model names
        """
        return list(self._models.keys())

    def get_prompt_config(self, model_name: str) -> "ModelPromptConfig":
        """Get prompt configuration for a model.

        Returns model-specific config if available, otherwise infers from name.

        Args:
            model_name: Model name (folder name)

        Returns:
            ModelPromptConfig instance
        """
        from .model_prompts import ModelPromptConfig, infer_prompt_config

        model = self.get_model(model_name)

        if model and model.argo_prompts:
            return model.argo_prompts

        # Infer from model name if not found
        return infer_prompt_config(model_name)

    def load_tokenizer(self, model: ModelConfig) -> Optional[Any]:
        """Load tokenizer for a model.

        Args:
            model: ModelConfig to load tokenizer for

        Returns:
            Tokenizer instance or None
        """
        if not model.has_tokenizer:
            self.logger.warning(f"Model {model.name} has no tokenizer files")
            return None

        try:
            from .tokenizer import TokenizerWrapper
            return TokenizerWrapper(str(model.path))
        except Exception as exc:
            self.logger.error(f"Failed to load tokenizer for {model.name}: {exc}")
            return None

    def load_tool_parser(self, model: ModelConfig) -> Optional[Any]:
        """Dynamically load model-specific tool parser.

        Args:
            model: ModelConfig with tool parser

        Returns:
            Tool parser class or None
        """
        if not model.has_tool_parser:
            self.logger.info(f"Model {model.name} has no custom tool parser, using default")
            # Return default XML parser
            from .tools.xml_parser import XMLToolParser
            return XMLToolParser

        try:
            parser_path = getattr(model, "tool_parser_path", None)
            if not parser_path:
                return None

            # Dynamically import the parser module
            spec = importlib.util.spec_from_file_location(
                f"{model.name}_parser", parser_path
            )
            if not spec or not spec.loader:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for parser class (typically named *ToolParser)
            for attr_name in dir(module):
                if "ToolParser" in attr_name or "Parser" in attr_name:
                    parser_class = getattr(module, attr_name)
                    if isinstance(parser_class, type):
                        self.logger.info(f"Loaded custom parser {attr_name} for {model.name}")
                        return parser_class

            self.logger.warning(f"No parser class found in {parser_path}")
            return None

        except Exception as exc:
            self.logger.error(f"Failed to load tool parser for {model.name}: {exc}")
            self.logger.info(f"Falling back to XMLToolParser for {model.name}")
            # Fall back to default XML parser
            from .tools.xml_parser import XMLToolParser
            return XMLToolParser

    def get_recommended_config(self, model: ModelConfig) -> Dict[str, Any]:
        """Get recommended configuration for a model.

        Combines extracted recommendations with sensible defaults.

        Args:
            model: ModelConfig

        Returns:
            Dictionary of recommended settings
        """
        # Defaults (Qwen3-Coder best practices as baseline)
        config = {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "repetition_penalty": 1.05,
            "max_tokens": 16384,
        }

        # Override with model-specific recommendations
        if model.recommended_temperature is not None:
            config["temperature"] = model.recommended_temperature
        if model.recommended_top_p is not None:
            config["top_p"] = model.recommended_top_p
        if model.recommended_top_k is not None:
            config["top_k"] = model.recommended_top_k
        if model.recommended_repetition_penalty is not None:
            config["repetition_penalty"] = model.recommended_repetition_penalty
        if model.recommended_max_tokens is not None:
            config["max_tokens"] = model.recommended_max_tokens

        return config

    def auto_configure(self, model_name: str) -> Dict[str, Any]:
        """Automatically configure all settings for a model.

        This is the main entry point for auto-detection.

        Args:
            model_name: Name of the model to configure

        Returns:
            Complete configuration dictionary with:
            - tokenizer: TokenizerWrapper or None
            - parser: Parser class or default
            - chat_template: Template string or None
            - sampling: Dictionary of sampling parameters

        Example:
            >>> registry = ModelRegistry()
            >>> config = registry.auto_configure("qwen3-coder-30b")
            >>> tokenizer = config["tokenizer"]
            >>> parser = config["parser"]()
        """
        model = self.get_model(model_name)

        if not model:
            self.logger.warning(
                f"Model {model_name} not found in registry, using defaults"
            )
            # Return default configuration
            from .tools.xml_parser import XMLToolParser
            return {
                "tokenizer": None,
                "parser": XMLToolParser,
                "chat_template": None,
                "sampling": {
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "top_k": 20,
                    "repetition_penalty": 1.05,
                    "max_tokens": 16384,
                },
            }

        # Load all components
        tokenizer = self.load_tokenizer(model) if model.has_tokenizer else None
        parser = self.load_tool_parser(model)

        config = {
            "tokenizer": tokenizer,
            "parser": parser,
            "chat_template": model.chat_template,
            "sampling": self.get_recommended_config(model),
            "model_config": model.model_config,
            "generation_config": model.generation_config,
        }

        self.logger.info(
            f"Auto-configured model {model_name}: "
            f"has_tokenizer={model.has_tokenizer}, "
            f"has_custom_parser={model.has_tool_parser}, "
            f"sampling={config['sampling']}"
        )

        return config


# Singleton instance for global use
_global_registry: Optional[ModelRegistry] = None


def get_global_registry(models_root: Optional[Path] = None) -> ModelRegistry:
    """Get or create the global model registry.

    Args:
        models_root: Optional models root directory

    Returns:
        Global ModelRegistry instance
    """
    global _global_registry

    if _global_registry is None:
        from .config import CONFIG
        root = models_root or CONFIG.paths.models_root
        _global_registry = ModelRegistry(root)

    return _global_registry
