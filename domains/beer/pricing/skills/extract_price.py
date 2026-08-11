"""extract_price: BaseSkill implementation for the PRC-001 "extract"
task.

Parses the raw payload from `collect` into structured fields matching
`domains/beer/pricing/prompts/extract_price.md`'s documented output
contract. A real implementation would invoke an LLM against that
prompt; no LLM-invocation infrastructure exists in core runtime yet,
so this sprint's implementation is a deterministic parser that honors
the same documented output shape — see that prompt file's
"Implementation note" and the Sprint 3 status notes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from core.context import ExecutionContext
from core.exceptions import WorkflowExecutionException


class ExtractPriceSkill:
    """Conforms to 05_Interface_Contract.md section 4.2's `BaseSkill`
    protocol."""

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        price_text = input_data.get("price_text")
        if price_text is None:
            raise WorkflowExecutionException(
                "collect payload missing 'price_text'",
                code="EXTRACT_PRICE_MISSING_FIELD",
            )
        try:
            price = float(str(price_text).replace(",", ""))
        except ValueError as exc:
            raise WorkflowExecutionException(
                f"could not parse price_text {price_text!r} as a number",
                code="EXTRACT_PRICE_PARSE_ERROR",
            ) from exc

        fetched_at = input_data.get("fetched_at")
        capture_time = (
            dt.datetime.fromtimestamp(float(fetched_at), tz=dt.UTC).isoformat()
            if fetched_at is not None
            else dt.datetime.now(tz=dt.UTC).isoformat()
        )

        return {
            "product_id": input_data.get("product_id"),
            "sku": input_data.get("sku"),
            "brand": input_data.get("brand"),
            "product_name": input_data.get("product_name"),
            "price": price,
            "currency": input_data.get("currency", "VND"),
            "store": input_data.get("store"),
            "province": input_data.get("province"),
            "capture_time": capture_time,
            "confidence": input_data.get("confidence", 0.9),
            "source_url": input_data.get("source_url"),
            "source": input_data.get("source"),
        }

    def rollback(self, context: dict[str, Any]) -> None:
        # Pure data transformation — no external side effects to
        # compensate for.
        return None


def make_extract_price_handler() -> Any:
    """Adapts ExtractPriceSkill to the TaskExecutor's TaskHandler
    calling convention."""
    skill = ExtractPriceSkill()

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raw_payload = task_input.get("raw_payload") or {}
        return skill.run(raw_payload)

    return handler


def make_extract_price_rollback() -> Any:
    """Adapts `ExtractPriceSkill.rollback()` to
    `core.workflow_engine.WorkflowEngine`'s compensation calling
    convention (a single `compensation_context: dict` argument). The
    method itself is a no-op (see its docstring) — this wrapper exists
    so the STRICT-policy compensation loop actually has something real
    to call for this task, not a placeholder."""
    skill = ExtractPriceSkill()

    def rollback(compensation_context: dict[str, Any]) -> None:
        skill.rollback(compensation_context)

    return rollback
