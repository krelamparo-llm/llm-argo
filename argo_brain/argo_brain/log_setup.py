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

    formatter = logging.Formatter(
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
