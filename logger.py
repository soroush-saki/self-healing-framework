"""
Structured logging utilities for the self-healing framework.

Provides consistent, structured logging with different severity levels
and optional JSON metadata attachment.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredLogger:
    """
    Logger that appends structured metadata (as JSON) to each log line.

    Output format:
        {timestamp} | {LEVEL} | {name} | {message} [ | Metadata: {json} ]
    """

    def __init__(self, name: str, level: int = logging.INFO):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.handlers.clear()

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self._logger.addHandler(handler)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def debug(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._emit(logging.DEBUG, message, metadata)

    def info(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._emit(logging.INFO, message, metadata)

    def warning(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._emit(logging.WARNING, message, metadata)

    def error(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._emit(logging.ERROR, message, metadata)

    def critical(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._emit(logging.CRITICAL, message, metadata)

    # ------------------------------------------------------------------
    # Private helper
    # ------------------------------------------------------------------

    def _emit(
        self, level: int, message: str, metadata: Optional[Dict[str, Any]]
    ) -> None:
        if metadata:
            self._logger.log(level, f"{message} | Metadata: {json.dumps(metadata)}")
        else:
            self._logger.log(level, message)


def get_logger(name: str, level: int = logging.INFO) -> StructuredLogger:
    """
    Factory function to create a StructuredLogger.

    Args:
        name:  Logger name (typically __name__).
        level: Logging level (default: INFO).

    Returns:
        Configured StructuredLogger instance.
    """
    return StructuredLogger(name, level)
