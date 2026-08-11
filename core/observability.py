"""Structured logging setup for the HMIP core runtime.

See 02_Runtime_Specification.md section 14. Minimum required log
fields: timestamp, execution_id, trace_id, component, event_type,
status, duration_ms, error_code.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(*, level: int = logging.INFO) -> None:
    """Configure process-wide structured JSON logging. Idempotent: safe
    to call multiple times during bootstrap."""
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(component: str) -> Any:
    """Return a structlog logger bound to a component name."""
    return structlog.get_logger().bind(component=component)


def log_event(
    logger: Any,
    *,
    event_type: str,
    status: str,
    execution_id: str | None = None,
    trace_id: str | None = None,
    duration_ms: float | None = None,
    error_code: str | None = None,
    **extra: Any,
) -> None:
    """Emit a structured log event carrying the spec's minimum field set."""
    logger.info(
        event_type,
        event_type=event_type,
        status=status,
        execution_id=execution_id,
        trace_id=trace_id,
        duration_ms=duration_ms,
        error_code=error_code,
        **extra,
    )
