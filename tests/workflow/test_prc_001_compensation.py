"""Integration test: STRICT compensation actually firing across
PRC-001's real domain handlers (not the generic core-level fixture
used elsewhere) — proves `registrar.py`'s wiring of `"rollback"` keys
for every task, plus `ExtractPriceSkill.rollback()` specifically,
works end-to-end through `WorkflowEngine`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.context import ExecutionContext
from core.registry import TaskRegistry
from core.workflow_engine import WorkflowEngine
from domains.beer.pricing.skills.collect_price import (
    make_collect_price_handler,
    make_collect_price_rollback,
)
from domains.beer.pricing.skills.enrich_price import (
    make_enrich_price_handler,
    make_enrich_price_rollback,
)
from domains.beer.pricing.skills.extract_price import (
    make_extract_price_handler,
    make_extract_price_rollback,
)
from domains.beer.pricing.skills.validate_price import (
    make_validate_price_handler,
    make_validate_price_rollback,
)

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / "domains"
    / "beer"
    / "pricing"
    / "workflows"
    / "WF-PRC-001.yaml"
)


def _registrar_with_failing_compare(registry: TaskRegistry) -> None:
    """Reuses the *real* collect/extract/validate/enrich handlers and
    their real rollbacks, then forces "compare" to fail — so
    compensation has genuine, previously-succeeded real tasks to roll
    back."""
    registry.register(
        {
            "name": "collect",
            "handler": make_collect_price_handler(),
            "rollback": make_collect_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "extract",
            "handler": make_extract_price_handler(),
            "rollback": make_extract_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "validate",
            "handler": make_validate_price_handler(),
            "rollback": make_validate_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "enrich",
            "handler": make_enrich_price_handler(),
            "rollback": make_enrich_price_rollback(),
        }
    )

    def fail_compare(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("simulated compare failure")

    def noop(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {}

    registry.register({"name": "compare", "handler": fail_compare})
    registry.register({"name": "decide", "handler": noop})
    registry.register({"name": "alert", "handler": noop})


def test_prc_001_compensation_rolls_back_real_completed_tasks_on_later_failure() -> None:
    engine = WorkflowEngine(
        workflow_lookup={"WF-PRC-001": WORKFLOW_PATH},
        task_registrar=_registrar_with_failing_compare,
    )
    workflow = engine.load("WF-PRC-001")

    record = engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert record["status"] == "FAILED"
    assert "simulated compare failure" in record["error"]
    assert record["compensation"]["triggered"] is True
    assert record["compensation"]["completed"] is True
    assert record["compensation"]["errors"] == []

    steps = [r.step for r in engine.lineage_tracer.list_records()]
    assert steps == [
        "collect",
        "extract",
        "validate",
        "enrich",
        "compare",
        "rollback:enrich",
        "rollback:validate",
        "rollback:extract",
        "rollback:collect",
    ]
