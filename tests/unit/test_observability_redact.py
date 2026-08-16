"""Unit tests for the logging redact processor (core/observability).

Closes the AGENTS.md security gap: config/logging.yaml declared
`redact_fields` but no code enforced it, so secrets passed to
`log_event(..., **extra)` leaked into structured logs.
"""

from __future__ import annotations

import io
import logging
from contextlib import redirect_stdout

import structlog

from core.observability import (
    _DEFAULT_REDACT_FIELDS,
    _redact_value,
    configure_logging,
    make_redact_processor,
)

REDACTED = "***REDACTED***"


def test_redact_value_replaces_sensitive_top_level_keys() -> None:
    fields = frozenset({"token", "password"})

    out = _redact_value({"token": "abc", "password": "secret", "ok": 1}, fields)

    assert out == {"token": REDACTED, "password": REDACTED, "ok": 1}


def test_redact_value_descends_into_nested_mappings() -> None:
    fields = frozenset({"api_key"})

    out = _redact_value(
        {"request": {"headers": {"api_key": "fc-123"}, "path": "/x"}},
        fields,
    )

    assert out["request"]["headers"]["api_key"] == REDACTED
    assert out["request"]["path"] == "/x"


def test_redact_value_descends_into_lists_and_tuples() -> None:
    fields = frozenset({"secret"})

    out = _redact_value({"items": [{"secret": "s"}, {"ok": 2}]}, fields)

    assert out["items"][0]["secret"] == REDACTED
    assert out["items"][1]["ok"] == 2


def test_redact_value_leaves_non_matching_data_unchanged() -> None:
    fields = frozenset({"token"})

    out = _redact_value({"a": [1, 2, {"b": 3}], "c": "d"}, fields)

    assert out == {"a": [1, 2, {"b": 3}], "c": "d"}


def test_make_redact_processor_scrubs_event_dict() -> None:
    proc = make_redact_processor(["token"])

    event = proc(None, "event", {"event": "login", "token": "abc", "user": "u"})

    assert event["token"] == REDACTED
    assert event["user"] == "u"
    assert event["event"] == "login"


def test_configure_logging_end_to_end_redacts_emitted_secret() -> None:
    # Reconfigure structlog with a known redact set and capture stdout.
    configure_logging(level=logging.INFO, redact_fields=("token",))
    logger = structlog.get_logger().bind(component="test")

    buf = io.StringIO()
    with redirect_stdout(buf):
        logger.info("auth", token="super-secret", user="alice")

    line = buf.getvalue().strip()
    assert "super-secret" not in line
    assert REDACTED in line
    assert '"user": "alice"' in line


def test_default_redact_fields_match_logging_yaml() -> None:
    # The hardcoded default must stay aligned with config/logging.yaml's
    # declared redact_fields so behavior matches the config even when the
    # config isn't wired in.
    assert set(_DEFAULT_REDACT_FIELDS) == {"password", "token", "secret", "api_key"}
