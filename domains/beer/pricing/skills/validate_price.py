"""validate_price: JSON-schema validation for PRC-001's "validate"
task (task type "schema_validate"), against
`domains/beer/pricing/schemas/schema.json` per
03_Domain_Specification.md section 10 ("Domain schema must match data
contract... Schema validation must be deterministic").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from core.context import ExecutionContext
from core.exceptions import WorkflowExecutionException

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "schema.json"


def _load_schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return data


def make_validate_price_handler() -> Any:
    """Adapts JSON-schema validation to the TaskExecutor's TaskHandler
    calling convention. The schema is loaded once, at registration
    time, not on every call."""
    schema = _load_schema()

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        structured = task_input.get("structured_price") or {}
        try:
            jsonschema.validate(instance=structured, schema=schema)
        except jsonschema.ValidationError as exc:
            raise WorkflowExecutionException(
                f"schema validation failed: {exc.message}",
                code="VALIDATE_PRICE_SCHEMA_MISMATCH",
            ) from exc
        return dict(structured)

    return handler


def make_validate_price_rollback() -> Any:
    """No-op: schema validation is a pure read/check, nothing to
    compensate. See `collect_price.py`'s `make_collect_price_rollback()`
    for why this is registered anyway."""

    def rollback(compensation_context: dict[str, Any]) -> None:
        return None

    return rollback
