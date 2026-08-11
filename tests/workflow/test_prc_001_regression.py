"""Regression tests for WorkflowEngine/PRC-001, pinning specific
historical bugs and edge-case behaviors so they cannot silently
reappear (08_Testing_Standard.md section 7: "Mỗi lỗi đã sửa phải có
test riêng để không tái diễn").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.context import ExecutionContext
from core.registry import TaskRegistry
from core.workflow_engine import WorkflowEngine

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / "domains"
    / "beer"
    / "pricing"
    / "workflows"
    / "WF-PRC-001.yaml"
)


def _ok_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
    return {"ok": True}


def test_regression_failing_task_is_still_recorded_in_lineage_before_halting() -> None:
    """Historical bug (Sprint 1, core/bootstrap.py): a failing
    bootstrap step used to raise before being appended to the report,
    silently dropping the failing step from the results entirely —
    fixed by making step execution always return a result instead of
    raising. This test pins the equivalent invariant for
    WorkflowEngine: a task that fails must still produce a lineage
    record (it ran and was observed), not vanish from the trace.
    """

    def fail_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("regression check: task must still be recorded")

    def registrar(registry: TaskRegistry) -> None:
        registry.register({"name": "collect", "handler": _ok_handler})
        registry.register({"name": "extract", "handler": fail_handler})
        for name in ("validate", "enrich", "compare", "decide", "alert"):
            registry.register({"name": name, "handler": _ok_handler})

    engine = WorkflowEngine(
        workflow_lookup={"WF-PRC-001": WORKFLOW_PATH}, task_registrar=registrar
    )
    workflow = engine.load("WF-PRC-001")

    record = engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert record["status"] == "FAILED"
    steps = [r.step for r in engine.lineage_tracer.list_records()]
    # "extract" (the failing task) is present — not silently missing.
    assert steps == ["collect", "extract"]


def test_regression_registry_reaches_terminal_failed_state_not_stuck_executing() -> None:
    """A failed execution must always leave its per-execution
    TaskRegistry in a terminal FAILED state, never left hanging in
    EXECUTING — a registry stuck mid-lifecycle would silently corrupt
    any future assumption that "not READY/FROZEN" implies "finished
    cleanly"."""
    captured: dict[str, TaskRegistry] = {}

    def registrar(registry: TaskRegistry) -> None:
        def fail_handler(
            task_input: dict[str, Any], context: ExecutionContext
        ) -> dict[str, Any]:
            raise RuntimeError("boom")

        for name in ("collect", "extract", "validate", "enrich", "compare", "decide", "alert"):
            registry.register({"name": name, "handler": fail_handler})
        captured["registry"] = registry

    engine = WorkflowEngine(
        workflow_lookup={"WF-PRC-001": WORKFLOW_PATH}, task_registrar=registrar
    )
    workflow = engine.load("WF-PRC-001")

    engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert captured["registry"].state == "FAILED"


def test_regression_successful_execution_reaches_terminal_completed_state() -> None:
    """Mirror of the above for the success path — a completed
    execution's registry must reach COMPLETED, not be left in
    EXECUTING."""
    captured: dict[str, TaskRegistry] = {}

    def registrar(registry: TaskRegistry) -> None:
        for name in ("collect", "extract", "validate", "enrich", "compare", "decide", "alert"):
            registry.register({"name": name, "handler": _ok_handler})
        captured["registry"] = registry

    engine = WorkflowEngine(
        workflow_lookup={"WF-PRC-001": WORKFLOW_PATH}, task_registrar=registrar
    )
    workflow = engine.load("WF-PRC-001")

    engine.execute(workflow, {"product_id": "P123", "source": "shopee", "market": "VN"})

    assert captured["registry"].state == "COMPLETED"


def test_regression_collect_task_input_resolves_from_caller_context_not_yaml_literal() -> None:
    """Pins the Sprint 3 design decision that `collect`'s
    `${product_id}`/`${source}`/`${market}` templates resolve against
    the caller-supplied `context` dict, not a hardcoded YAML literal —
    a regression here would silently make every PRC-001 run collect
    the same product regardless of what the caller asked for."""
    seen_inputs: list[dict[str, Any]] = []

    def collect_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        seen_inputs.append(task_input)
        return {"price_text": "1", "fetched_at": 0.0}

    def registrar(registry: TaskRegistry) -> None:
        registry.register({"name": "collect", "handler": collect_handler})
        for name in ("extract", "validate", "enrich", "compare", "decide", "alert"):
            registry.register({"name": name, "handler": _ok_handler})

    engine = WorkflowEngine(
        workflow_lookup={"WF-PRC-001": WORKFLOW_PATH}, task_registrar=registrar
    )
    workflow = engine.load("WF-PRC-001")

    engine.execute(
        workflow, {"product_id": "DIFFERENT_PRODUCT", "source": "different_source", "market": "US"}
    )

    assert seen_inputs == [
        {
            "product_id": "DIFFERENT_PRODUCT",
            "source": "different_source",
            "market": "US",
        }
    ]
