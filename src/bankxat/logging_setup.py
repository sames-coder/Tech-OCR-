"""PII xavfsiz strukturali logging sozlamasi."""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

from bankxat.security import redact_value


def _redact_processor(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """Strukturali log hodisasidan sezgir ma'lumotlarni olib tashlaydi."""

    redacted = redact_value(event_dict)
    return dict(redacted)


def configure_logging(level: int = logging.INFO) -> None:
    """Konsol uchun ixcham va PII xavfsiz loggingni yoqadi."""

    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
