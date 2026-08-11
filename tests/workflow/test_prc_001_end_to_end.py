"""End-to-end test for PRC-001 (03_Domain_Specification.md section 6 /
15_Acceptance_Criteria.md section 3, Sprint 3: "Workflow PRC-001 chạy
end-to-end... Lineage được ghi nhận... Workflow test pass").

This is the one test in the whole suite allowed to depend on both
`core.workflow_engine` and the `domains.beer.pricing` domain pack —
everywhere else, core and domain tests stay separated.
"""

from __future__ import annotations

from pathlib import Path

from core.models import DECISION_ALERT, DECISION_ESCALATE, DECISION_IGNORE
from core.registry import TaskRegistry
from core.workflow_engine import WorkflowEngine
from domains.beer.pricing.registrar import register_prc_001_tasks

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / "domains"
    / "beer"
    / "pricing"
    / "workflows"
    / "WF-PRC-001.yaml"
)


def _engine(*, base_price: float = 18000.0) -> WorkflowEngine:
    def registrar(registry: TaskRegistry) -> None:
        register_prc_001_tasks(registry, base_price=base_price)

    return WorkflowEngine(
        workflow_lookup={"WF-PRC-001": WORKFLOW_PATH},
        task_registrar=registrar,
    )


def test_prc_001_runs_end_to_end_and_completes() -> None:
    engine = _engine()
    workflow = engine.load("WF-PRC-001")

    record = engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert record["status"] == "COMPLETED"
    assert record["error"] is None
    assert record["workflow_id"] == "WF-PRC-001"


def test_prc_001_decision_reflects_price_variance() -> None:
    # Mock collect payload resolves to price 18500 (see
    # domains/beer/pricing/skills/collect_price.py's mock data).
    # base_price=18500 -> ~0% variance -> IGNORE.
    engine = _engine(base_price=18500.0)
    workflow = engine.load("WF-PRC-001")

    record = engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert record["output"]["decision"] == DECISION_IGNORE


def test_prc_001_decision_alerts_on_moderate_variance() -> None:
    # 18500 vs base 17500 -> ~5.7% variance -> ALERT.
    engine = _engine(base_price=17500.0)
    workflow = engine.load("WF-PRC-001")

    record = engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert record["output"]["decision"] == DECISION_ALERT


def test_prc_001_decision_escalates_on_large_variance() -> None:
    # 18500 vs base 15000 -> ~23% variance -> ESCALATE.
    engine = _engine(base_price=15000.0)
    workflow = engine.load("WF-PRC-001")

    record = engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert record["output"]["decision"] == DECISION_ESCALATE


def test_prc_001_records_lineage_for_every_step() -> None:
    engine = _engine()
    workflow = engine.load("WF-PRC-001")

    engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    steps = [r.step for r in engine.lineage_tracer.list_records()]
    assert steps == ["collect", "extract", "validate", "enrich", "compare", "decide", "alert"]


def test_prc_001_enrich_fills_in_sku_from_ontology() -> None:
    """Sprint 3's mock collect payload doesn't provide a sku (see
    SPRINT_3_PRC001_STATUS.md) — "enrich" fills it in from
    knowledge/master/skus.json."""
    engine = _engine()
    workflow = engine.load("WF-PRC-001")

    engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    records = {r.step: r for r in engine.lineage_tracer.list_records()}
    assert records["enrich"].output_value["sku"] == "SKU-P123-330"


def test_prc_001_publishes_task_completed_events_for_every_step() -> None:
    engine = _engine()
    workflow = engine.load("WF-PRC-001")
    received: list[dict[str, object]] = []
    engine.event_bus.subscribe("task_completed", received.append)

    engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert [e["task_id"] for e in received] == [
        "collect",
        "extract",
        "validate",
        "enrich",
        "compare",
        "decide",
        "alert",
    ]


def test_prc_001_fails_gracefully_for_unknown_product() -> None:
    engine = _engine()
    workflow = engine.load("WF-PRC-001")

    record = engine.execute(
        workflow, {"product_id": "UNKNOWN_PRODUCT", "source": "shopee", "market": "VN"}
    )

    assert record["status"] == "FAILED"
    assert record["error"] is not None
    # Only "collect" should have run before failing.
    steps = [r.step for r in engine.lineage_tracer.list_records()]
    assert steps == ["collect"]
