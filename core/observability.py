"""Structured logging setup for the HMIP core runtime.

See 02_Runtime_Specification.md section 14. Minimum required log
fields: timestamp, execution_id, trace_id, component, event_type,
status, duration_ms, error_code.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterable
from typing import Any

import structlog

# Default redact field names — kept in sync with config/logging.yaml's
# `redact_fields` so the config declaration and the runtime behavior
# match even when the config isn't wired into configure_logging()
# (e.g. extensions/ sets up logging independently). Override at runtime
# via HMIP_LOG_REDACT_FIELDS (comma-separated).
_DEFAULT_REDACT_FIELDS: tuple[str, ...] = ("password", "token", "secret", "api_key")
_REDACTED = "***REDACTED***"


def _parse_redact_fields() -> tuple[str, ...]:
    env_val = os.environ.get("HMIP_LOG_REDACT_FIELDS")
    if env_val is not None and env_val.strip():
        return tuple(f.strip() for f in env_val.split(",") if f.strip())
    return _DEFAULT_REDACT_FIELDS


def _redact_value(value: Any, fields: frozenset[str]) -> Any:
    """Recursively replace values of redact-sensitive keys in nested
    mappings/sequences. Non-matching data passes through unchanged."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k in fields else _redact_value(v, fields))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        redacted = [_redact_value(v, fields) for v in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    return value


def make_redact_processor(fields: Iterable[str]) -> Any:
    """Build a structlog processor that scrubs values of sensitive keys
    from the event dict (and any nested mappings within it). Without
    this, config/logging.yaml's `redact_fields` declaration was inert
    — secrets handed to `log_event(..., **extra)` leaked into logs."""
    sensitive = frozenset(fields)

    def redact_processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return dict(_redact_value(event_dict, sensitive))

    return redact_processor


def configure_logging(
    *,
    level: int = logging.INFO,
    redact_fields: Iterable[str] | None = None,
) -> None:
    """Configure process-wide structured JSON logging. Idempotent: safe
    to call multiple times during bootstrap.

    `redact_fields` defaults to the env/config-derived set (see
    `_parse_redact_fields`); pass an explicit iterable to override
    (e.g. from the frozen config's `logging.redact_fields`)."""
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")

    fields = tuple(redact_fields) if redact_fields is not None else _parse_redact_fields()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            make_redact_processor(fields),
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
