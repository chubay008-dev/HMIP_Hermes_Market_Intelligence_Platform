"""alert_price: notify/escalate handler for PRC-001's "alert" task
(task type "notify").
"""

from __future__ import annotations

from typing import Any

from core.context import ExecutionContext
from core.models import DECISION_IGNORE


def make_alert_handler() -> Any:
    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        decision_result = task_input.get("decision_result") or {}
        decision = decision_result.get("decision", DECISION_IGNORE)
        if decision == DECISION_IGNORE:
            return {"notified": False, "decision": decision}
        return {
            "notified": True,
            "decision": decision,
            "recommended_action": decision_result.get("recommended_action"),
            "reason": decision_result.get("reason"),
        }

    return handler


def make_alert_rollback() -> Any:
    """No-op in this vertical slice: this task's handler doesn't
    actually send anything external — it returns a dict describing
    what *would* be sent (see SPRINT_3_PRC001_STATUS.md) — so there is
    no real notification to retract yet. Once a real notification
    channel exists, this should send a retraction/cancellation
    message for any `decision != IGNORE` alert that was actually
    dispatched."""

    def rollback(compensation_context: dict[str, Any]) -> None:
        return None

    return rollback
