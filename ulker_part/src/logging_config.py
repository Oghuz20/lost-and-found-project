"""Logging configuration for the Smart Lost & Found application.

This module sets up structured logging with appropriate levels and formatters
for different environments (development, testing, production).
"""

from __future__ import annotations

import logging
import logging.config
import os
import sys
from typing import Dict, Any


def setup_logging(
    level: str = "INFO",
    format_string: str | None = None,
    enable_json: bool = False
) -> None:
    """Set up application logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string for log messages
        enable_json: Whether to output logs in JSON format
    """
    # Determine log level from environment or parameter
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Default format if not provided
    if format_string is None:
        if enable_json:
            format_string = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", ' \
                           '"name": "%(name)s", "message": "%(message)s"}'
        else:
            format_string = (
                "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
            )

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format=format_string,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True  # Override any existing configuration
    )

    # Set specific logger levels for noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Log that logging has been configured
    logger = logging.getLogger(__name__)
    logger.debug("Logging configured with level=%s", level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds contextual information to log messages."""

    def process(self, msg, kwargs):
        # Add any extra context from self.extra to the log record
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        kwargs["extra"].update(self.extra)
        return msg, kwargs