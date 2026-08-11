"""compare_price: variance calculation for PRC-001's "compare" task.

Task type "transform" per 03_Domain_Specification.md section 5. Pure
data transformation — no decision-making (that belongs to
`decision_engine.py`, per section 7's rule that the decision engine
owns threshold logic).
"""

from __future__ import annotations

from typing import Any

from core.context import ExecutionContext
from core.exceptions import WorkflowExecutionException


def compute_variance(current_price: float, base_price: float) -> dict[str, Any]:
    if base_price <= 0:
        raise WorkflowExecutionException(
            f"base_price must be > 0, got {base_price}",
            code="COMPARE_PRICE_INVALID_BASE",
        )
    delta = current_price - base_price
    delta_percent = (delta / base_price) * 100
    return {
        "current_price": current_price,
        "base_price": base_price,
        "delta": delta,
        "delta_percent": delta_percent,
    }


def make_compare_price_handler(base_price: float) -> Any:
    """`base_price` is bound at registration time — a real deployment
    would resolve it per-product from a reference-price source; that
    lookup is out of scope for this vertical slice."""

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        validated = task_input.get("validated_price") or {}
        current_price = validated.get("price")
        if current_price is None:
            raise WorkflowExecutionException(
                "validated_price payload missing 'price'",
                code="COMPARE_PRICE_MISSING_PRICE",
            )
        result = compute_variance(float(current_price), base_price)
        result["confidence"] = validated.get("confidence", 0.9)
        return result

    return handler


def make_compare_price_rollback() -> Any:
    """No-op: variance calculation is a pure computation, nothing to
    compensate. See `collect_price.py`'s `make_collect_price_rollback()`
    for why this is registered anyway."""

    def rollback(compensation_context: dict[str, Any]) -> None:
        return None

    return rollback
