"""Structured logging with a redaction processor so secrets never hit the logs."""
from __future__ import annotations

import logging
import re

import structlog

from .config import get_settings

# Patterns that must never appear in logs even if accidentally passed in.
_REDACT = re.compile(
    r"(token|secret|password|api[_-]?key|authorization|bearer)", re.IGNORECASE
)


def _redact(_, __, event_dict: dict) -> dict:
    for k in list(event_dict.keys()):
        if _REDACT.search(k):
            event_dict[k] = "***REDACTED***"
    return event_dict


def configure_logging() -> None:
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _redact,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
