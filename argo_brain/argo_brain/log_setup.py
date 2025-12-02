"""Centralized logging utilities for Argo Brain."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import CONFIG

_LOGGER: Optional[logging.Logger] = None


def setup_logging(level: str | int = "INFO") -> logging.Logger:
    """Configure application-wide logging and return the root logger."""

    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    log_dir = CONFIG.paths.state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "argo_brain.log"

    logger = logging.getLogger("argo_brain")
    logger.setLevel(level if isinstance(level, int) else getattr(logging, str(level).upper(), logging.INFO))

    # Custom formatter that includes extra fields like elapsed_ms, tokens, and tool info
    class ExtraFormatter(logging.Formatter):
        def format(self, record):
            # Add extra fields to message if they exist
            extras = []
            if hasattr(record, 'elapsed_ms'):
                extras.append(f"elapsed_ms={record.elapsed_ms}")

            # Token counts (NEW)
            if hasattr(record, 'prompt_tokens') and record.prompt_tokens:
                extras.append(f"prompt_tokens={record.prompt_tokens}")
            if hasattr(record, 'completion_tokens') and record.completion_tokens:
                extras.append(f"completion_tokens={record.completion_tokens}")
            if hasattr(record, 'total_tokens') and record.total_tokens:
                extras.append(f"total_tokens={record.total_tokens}")

            if hasattr(record, 'tokens_max'):
                extras.append(f"tokens_max={record.tokens_max}")
            if hasattr(record, 'status_code'):
                extras.append(f"status={record.status_code}")
            if hasattr(record, 'session_id'):
                extras.append(f"session={record.session_id}")
            if hasattr(record, 'tool'):
                extras.append(f"tool={record.tool}")
            if hasattr(record, 'chars'):
                extras.append(f"chars={record.chars}")

            if extras:
                record.msg = f"{record.msg} [{', '.join(extras)}]"

            return super().format(record)

    formatter = ExtraFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if os.environ.get("ARGO_LOG_TO_STDOUT", "0") == "1":
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logger.debug("Logging initialized at %s", log_path)
    _LOGGER = logger
    return logger
