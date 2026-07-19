#!/usr/bin/env python3
"""Structured JSON logging with correlation ID support.

Provides consistent JSON log format across all services with:
- Correlation ID propagation via contextvars
- Structured fields for easy querying
- Service identification
- Log level mapping
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Context variable for correlation ID propagation across async boundaries
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
_service_name: contextvars.ContextVar[str] = contextvars.ContextVar("service_name", default="unknown")

# Global start time for uptime calculation
_start_time = time.time()


class JSONFormatter(logging.Formatter):
    """JSON log formatter with structured fields."""

    def __init__(self, service_name: str = "unknown", include_extra: bool = True):
        super().__init__()
        self.service_name = service_name
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        # Get correlation ID from context
        corr_id = _correlation_id.get()
        if not corr_id:
            corr_id = str(uuid.uuid4())[:8]
            _correlation_id.set(corr_id)

        # Get service name from context or fallback
        service = _service_name.get() or self.service_name

        # Base log entry
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": service,
            "trace_id": corr_id,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add source location
        log_entry["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add process/thread info
        log_entry["process"] = {
            "pid": record.process,
            "thread": record.thread,
            "thread_name": record.threadName,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None,
            }

        # Add extra fields from record
        if self.include_extra:
            extra = {}
            for key, value in record.__dict__.items():
                if key not in {
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "message", "name", "pathname", "process", "processName",
                    "relativeCreated", "thread", "threadName", "exc_info",
                    "exc_text", "stack_info", "getMessage"
                }:
                    try:
                        # Ensure JSON serializable
                        json.dumps(value)
                        extra[key] = value
                    except (TypeError, ValueError):
                        extra[key] = str(value)
            if extra:
                log_entry["extra"] = extra

        return json.dumps(log_entry, separators=(",", ":"))


def setup_logging(
    service_name: str,
    level: Union[int, str] = logging.INFO,
    json_output: bool = True,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """Configure structured logging for a service.

    Args:
        service_name: Name of the service (e.g., "camera_node", "control", "reid")
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_output: Whether to output JSON (True) or human-readable (False)
        log_file: Optional file path for log output

    Returns:
        Configured logger instance
    """
    # Set service name in context
    _service_name.set(service_name)

    logger = logging.getLogger(service_name)
    logger.setLevel(level)
    logger.handlers.clear()  # Remove any existing handlers

    # Prevent propagation to root logger
    logger.propagate = False

    if json_output:
        formatter = JSONFormatter(service_name=service_name)
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "app") -> logging.Logger:
    """Get a logger with the current service context."""
    return logging.getLogger(name)


def set_correlation_id(corr_id: Optional[str] = None) -> str:
    """Set or generate a correlation ID.

    Args:
        corr_id: Optional correlation ID to set. If None, generates a new UUID.

    Returns:
        The correlation ID that was set.
    """
    if corr_id is None:
        corr_id = str(uuid.uuid4())
    _correlation_id.set(corr_id)
    return corr_id


def get_correlation_id() -> str:
    """Get the current correlation ID, generating one if not set."""
    corr_id = _correlation_id.get()
    if not corr_id:
        corr_id = str(uuid.uuid4())[:8]
        _correlation_id.set(corr_id)
    return corr_id


def set_service_name(name: str) -> None:
    """Set the service name for the current context."""
    _service_name.set(name)


class LogContext:
    """Context manager for adding structured context to logs."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.old_extra = {}

    def __enter__(self):
        # Store current extra on the logger
        logger = logging.getLogger()
        self.old_extra = getattr(logger, "_structured_extra", {})
        logger._structured_extra = {**self.old_extra, **self.kwargs}
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger = logging.getLogger()
        logger._structured_extra = self.old_extra


def log_with_context(logger: logging.Logger, level: int, message: str, **kwargs) -> None:
    """Log a message with structured context.

    Args:
        logger: Logger instance
        level: Log level (logging.INFO, etc.)
        message: Log message
        **kwargs: Additional structured fields to include
    """
    # Create a LogRecord with extra fields
    extra = {"structured_extra": kwargs}
    logger.log(level, message, extra=extra)


# Convenience functions
def debug(logger: logging.Logger, message: str, **kwargs) -> None:
    log_with_context(logger, logging.DEBUG, message, **kwargs)


def info(logger: logging.Logger, message: str, **kwargs) -> None:
    log_with_context(logger, logging.INFO, message, **kwargs)


def warning(logger: logging.Logger, message: str, **kwargs) -> None:
    log_with_context(logger, logging.WARNING, message, **kwargs)


def error(logger: logging.Logger, message: str, **kwargs) -> None:
    log_with_context(logger, logging.ERROR, message, **kwargs)


def critical(logger: logging.Logger, message: str, **kwargs) -> None:
    log_with_context(logger, logging.CRITICAL, message, **kwargs)


def exception(logger: logging.Logger, message: str, **kwargs) -> None:
    log_with_context(logger, logging.ERROR, message, exc_info=True, **kwargs)


__all__ = [
    "JSONFormatter",
    "setup_logging",
    "get_logger",
    "set_correlation_id",
    "get_correlation_id",
    "set_service_name",
    "LogContext",
    "log_with_context",
    "debug",
    "info",
    "warning",
    "error",
    "critical",
    "exception",
]