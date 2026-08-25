"""Application logging setup."""

from __future__ import annotations

import sys

from loguru import logger

LOG_FORMAT = "<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message} | {extra}"
VALID_LOG_LEVELS = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}


def configure_logging(level: str = "INFO") -> None:
    """Configure Loguru for CLI runs."""

    normalized_level = level.upper()
    if normalized_level not in VALID_LOG_LEVELS:
        valid = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ValueError(f"Unsupported log level {level!r}; expected one of: {valid}")

    logger.remove()
    logger.enable("marketlab")
    logger.add(
        sys.stderr,
        level=normalized_level,
        format=LOG_FORMAT,
        colorize=True,
    )
