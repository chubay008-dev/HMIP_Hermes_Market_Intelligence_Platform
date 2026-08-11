"""PricingDecisionEngine: PRC-001's decision engine.

Conforms to 05_Interface_Contract.md section 4.9's `DecisionEngine`
protocol (`evaluate(current_price, base_price) -> str`) plus a
domain-specific `build_decision_result()` helper that wraps
`evaluate()` into a full `core.models.DecisionResult`
(confidence/reason/recommended_action) — the Protocol itself only
returns the bare decision string; section 9's "không thêm method
ngoài contract" governs the *Protocol* surface, not what a concrete
domain implementation class may additionally expose.
"""

from __future__ import annotations

from typing import Any

from core.context import ExecutionContext
from core.exceptions import DecisionEngineException, WorkflowExecutionException
from core.models import (
    DECISION_ALERT,
    DECISION_ESCALATE,
    DECISION_HUMAN_REVIEW,
    DECISION_IGNORE,
    DecisionResult,
)

# Explicit thresholds (05_Interface_Contract.md section 4.9's rule:
# "Phải có threshold rõ ràng").
ALERT_THRESHOLD_PERCENT = 5.0
ESCALATE_THRESHOLD_PERCENT = 10.0
LOW_CONFIDENCE_THRESHOLD = 0.7

_RECOMMENDED_ACTIONS: dict[str, str | None] = {
    DECISION_IGNORE: None,
    DECISION_ALERT: "notify_pricing_team",
    DECISION_ESCALATE: "escalate_to_category_manager",
    DECISION_HUMAN_REVIEW: "route_to_human_review_queue",
}


class PricingDecisionEngine:
    """Conforms to the `DecisionEngine` protocol."""

    def evaluate(self, current_price: float, base_price: float) -> str:
        """Section 4.9 rules: must handle `base_price <= 0`, must not
        mutate input (both args are floats — immutable, nothing to
        mutate), must only return an allowed decision value."""
        if base_price <= 0:
            raise DecisionEngineException(
                f"base_price must be > 0, got {base_price}",
                code="DECISION_ENGINE_INVALID_BASE_PRICE",
            )
        variance_percent = abs((current_price - base_price) / base_price) * 100
        if variance_percent >= ESCALATE_THRESHOLD_PERCENT:
            return DECISION_ESCALATE
        if variance_percent >= ALERT_THRESHOLD_PERCENT:
            return DECISION_ALERT
        return DECISION_IGNORE

    def build_decision_result(
        self, current_price: float, base_price: float, *, confidence: float = 0.9
    ) -> DecisionResult:
        """Wraps `evaluate()` into a full DecisionResult, applying the
        confidence-based human-review override per
        03_Domain_Specification.md section 7 ("Confidence below
        threshold must route to human review or escalation")."""
        decision = self.evaluate(current_price, base_price)
        variance_percent = abs((current_price - base_price) / base_price) * 100

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            decision = DECISION_HUMAN_REVIEW
            reason = (
                f"confidence {confidence:.2f} below threshold "
                f"{LOW_CONFIDENCE_THRESHOLD}; variance {variance_percent:.1f}%"
            )
        else:
            reason = f"price variance {variance_percent:.1f}% vs base {base_price}"

        return DecisionResult(
            decision=decision,
            confidence=confidence,
            reason=reason,
            recommended_action=_RECOMMENDED_ACTIONS[decision],
        )


def make_decide_handler(base_price: float) -> Any:
    """Adapts PricingDecisionEngine to the TaskExecutor's TaskHandler
    calling convention."""
    engine = PricingDecisionEngine()

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        compare_result = task_input.get("compare_result") or {}
        current_price = compare_result.get("current_price")
        confidence = compare_result.get("confidence", 0.9)
        if current_price is None:
            raise WorkflowExecutionException(
                "compare_result missing 'current_price'",
                code="DECIDE_MISSING_PRICE",
            )
        result = engine.build_decision_result(
            float(current_price), base_price, confidence=float(confidence)
        )
        return {
            "decision": result.decision,
            "confidence": result.confidence,
            "reason": result.reason,
            "recommended_action": result.recommended_action,
        }

    return handler


def make_decide_rollback() -> Any:
    """No-op: decision evaluation is a pure computation, nothing to
    compensate. See `domains/beer/pricing/skills/collect_price.py`'s
    `make_collect_price_rollback()` for why this is registered
    anyway."""

    def rollback(compensation_context: dict[str, Any]) -> None:
        return None

    return rollback
