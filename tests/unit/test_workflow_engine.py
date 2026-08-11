"""Unit tests for WorkflowEngine (05_Interface_Contract.md section
4.3), using the generic linear fixture — core-level tests must not
depend on domain code (03_Domain_Specification.md section 2: "Core
runtime không chứa rule nghiệp vụ đặc thù ngành" applies symmetrically
to core's own test suite)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.context import ExecutionContext
from core.exceptions import WorkflowExecutionException, WorkflowParseException
from core.lineage import PersistentLineageTracer
from core.registry import TaskRegistry
from core.workflow_engine import WorkflowEngine

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "integration" / "fixtures"
FIXTURE_PATH = _FIXTURES_DIR / "generic_linear_workflow.yaml"


def _noop_registrar(registry: TaskRegistry) -> None:
    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True}

    for name in ("collect", "extract", "validate", "compare", "decide", "alert"):
        registry.register({"name": name, "handler": handler})


def _engine() -> WorkflowEngine:
    return WorkflowEngine(
        workflow_lookup={"WF-TEST-001": FIXTURE_PATH},
        task_registrar=_noop_registrar,
    )


def test_load_returns_parsed_dict_for_known_id() -> None:
    engine = _engine()

    raw = engine.load("WF-TEST-001")

    assert raw["id"] == "WF-TEST-001"
    assert len(raw["tasks"]) == 6


def test_load_raises_for_unknown_workflow_id() -> None:
    engine = _engine()

    with pytest.raises(WorkflowParseException):
        engine.load("WF-DOES-NOT-EXIST")


def test_execute_runs_all_tasks_and_returns_completed() -> None:
    engine = _engine()
    raw = engine.load("WF-TEST-001")

    record = engine.execute(raw, {"some_input": "value"})

    assert record["status"] == "COMPLETED"
    assert record["workflow_id"] == "WF-TEST-001"
    assert record["error"] is None
    assert record["execution_id"]
    assert record["trace_id"]
    assert record["input"] == {"some_input": "value"}


def test_execute_records_lineage_for_every_task() -> None:
    engine = _engine()
    raw = engine.load("WF-TEST-001")

    engine.execute(raw, {})

    records = engine.lineage_tracer.list_records()
    expected_steps = ["collect", "extract", "validate", "compare", "decide", "alert"]
    assert [r.step for r in records] == expected_steps


def test_execute_publishes_task_completed_events() -> None:
    engine = _engine()
    raw = engine.load("WF-TEST-001")
    received: list[dict[str, Any]] = []
    engine.event_bus.subscribe("task_completed", received.append)

    engine.execute(raw, {})

    assert [e["task_id"] for e in received] == [
        "collect",
        "extract",
        "validate",
        "compare",
        "decide",
        "alert",
    ]


def test_execute_stops_and_reports_failure_on_task_error() -> None:
    def failing_registrar(registry: TaskRegistry) -> None:
        def ok_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
            return {"ok": True}

        def fail_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
            raise RuntimeError("boom")

        registry.register({"name": "collect", "handler": ok_handler})
        registry.register({"name": "extract", "handler": fail_handler})
        for name in ("validate", "compare", "decide", "alert"):
            registry.register({"name": name, "handler": ok_handler})

    engine = WorkflowEngine(
        workflow_lookup={"WF-TEST-001": FIXTURE_PATH}, task_registrar=failing_registrar
    )
    raw = engine.load("WF-TEST-001")

    record = engine.execute(raw, {})

    assert record["status"] == "FAILED"
    assert record["error"] is not None
    assert "boom" in record["error"]

    # Only collect + extract should have run before the loop stopped.
    task_names = [r.step for r in engine.lineage_tracer.list_records()]
    assert task_names == ["collect", "extract"]


def test_execute_raises_workflow_parse_exception_for_invalid_workflow() -> None:
    engine = _engine()

    with pytest.raises(WorkflowParseException):
        engine.execute({"id": "BAD", "version": "1.0.0", "owner": "x", "tasks": []}, {})


def test_execute_raises_workflow_execution_exception_on_event_delivery_failure() -> None:
    engine = _engine()
    raw = engine.load("WF-TEST-001")

    def broken_subscriber(event: dict[str, Any]) -> None:
        raise RuntimeError("subscriber exploded")

    engine.event_bus.subscribe("task_completed", broken_subscriber)

    with pytest.raises(WorkflowExecutionException):
        engine.execute(raw, {})


def test_cancel_does_not_raise() -> None:
    engine = _engine()

    engine.cancel("some-execution-id")  # must not raise


def test_execute_with_persistent_lineage_tracer_writes_to_disk(tmp_path: Path) -> None:
    tracer = PersistentLineageTracer(tmp_path / "lineage.jsonl")
    engine = WorkflowEngine(
        workflow_lookup={"WF-TEST-001": FIXTURE_PATH},
        task_registrar=_noop_registrar,
        lineage_tracer=tracer,
    )
    raw = engine.load("WF-TEST-001")

    engine.execute(raw, {})

    # Re-read from a fresh tracer instance to prove it's real file
    # persistence, not just the same in-process object.
    reread = PersistentLineageTracer(tmp_path / "lineage.jsonl")
    steps = [r.step for r in reread.list_records()]
    assert steps == ["collect", "extract", "validate", "compare", "decide", "alert"]


# --- STRICT compensation --------------------------------------------------


def test_compensation_calls_rollback_on_previously_succeeded_tasks_in_reverse_order() -> None:
    rollback_calls: list[str] = []

    def ok_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True}

    def fail_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("boom")

    def make_rollback(name: str) -> Any:
        def rollback(compensation_context: dict[str, Any]) -> None:
            rollback_calls.append(name)

        return rollback

    def registrar(registry: TaskRegistry) -> None:
        registry.register(
            {"name": "collect", "handler": ok_handler, "rollback": make_rollback("collect")}
        )
        registry.register(
            {"name": "extract", "handler": ok_handler, "rollback": make_rollback("extract")}
        )
        registry.register(
            {"name": "validate", "handler": ok_handler, "rollback": make_rollback("validate")}
        )
        # "compare" fails — nothing after it ever runs.
        registry.register({"name": "compare", "handler": fail_handler})
        for name in ("decide", "alert"):
            registry.register({"name": name, "handler": ok_handler})

    engine = WorkflowEngine(workflow_lookup={"WF-TEST-001": FIXTURE_PATH}, task_registrar=registrar)
    raw = engine.load("WF-TEST-001")

    record = engine.execute(raw, {})

    assert record["status"] == "FAILED"
    assert record["compensation"]["triggered"] is True
    assert record["compensation"]["completed"] is True
    assert record["compensation"]["errors"] == []
    # Reverse execution order — validate rolled back first, collect last.
    assert rollback_calls == ["validate", "extract", "collect"]


def test_compensation_skips_tasks_with_no_registered_rollback() -> None:
    def ok_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True}

    def fail_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("boom")

    def registrar(registry: TaskRegistry) -> None:
        registry.register({"name": "collect", "handler": ok_handler})  # no rollback key
        registry.register({"name": "extract", "handler": fail_handler})
        for name in ("validate", "compare", "decide", "alert"):
            registry.register({"name": name, "handler": ok_handler})

    engine = WorkflowEngine(workflow_lookup={"WF-TEST-001": FIXTURE_PATH}, task_registrar=registrar)
    raw = engine.load("WF-TEST-001")

    record = engine.execute(raw, {})

    assert record["status"] == "FAILED"
    assert record["compensation"]["triggered"] is True
    assert record["compensation"]["completed"] is True
    assert record["compensation"]["errors"] == []


def test_compensation_collects_rollback_failures_without_stopping_the_rest() -> None:
    rollback_calls: list[str] = []

    def ok_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True}

    def fail_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("boom")

    def broken_rollback(compensation_context: dict[str, Any]) -> None:
        raise RuntimeError("rollback itself failed")

    def healthy_rollback(compensation_context: dict[str, Any]) -> None:
        rollback_calls.append(compensation_context["task_id"])

    def registrar(registry: TaskRegistry) -> None:
        registry.register({"name": "collect", "handler": ok_handler, "rollback": healthy_rollback})
        registry.register({"name": "extract", "handler": ok_handler, "rollback": broken_rollback})
        registry.register(
            {"name": "validate", "handler": ok_handler, "rollback": healthy_rollback}
        )
        registry.register({"name": "compare", "handler": fail_handler})
        for name in ("decide", "alert"):
            registry.register({"name": name, "handler": ok_handler})

    engine = WorkflowEngine(workflow_lookup={"WF-TEST-001": FIXTURE_PATH}, task_registrar=registrar)
    raw = engine.load("WF-TEST-001")

    record = engine.execute(raw, {})

    assert record["compensation"]["triggered"] is True
    assert record["compensation"]["completed"] is False
    assert len(record["compensation"]["errors"]) == 1
    assert record["compensation"]["errors"][0]["task_id"] == "extract"
    # "collect" and "validate" still got rolled back despite "extract"'s
    # rollback failing in between.
    assert set(rollback_calls) == {"collect", "validate"}


def test_compensation_not_triggered_on_successful_execution() -> None:
    engine = _engine()
    raw = engine.load("WF-TEST-001")

    record = engine.execute(raw, {})

    assert record["status"] == "COMPLETED"
    assert record["compensation"] == {"triggered": False, "completed": True, "errors": []}


def test_compensation_records_lineage_for_each_rollback() -> None:
    def ok_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True}

    def fail_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("boom")

    def rollback(compensation_context: dict[str, Any]) -> None:
        return None

    def registrar(registry: TaskRegistry) -> None:
        registry.register({"name": "collect", "handler": ok_handler, "rollback": rollback})
        registry.register({"name": "extract", "handler": fail_handler})
        for name in ("validate", "compare", "decide", "alert"):
            registry.register({"name": name, "handler": ok_handler})

    engine = WorkflowEngine(workflow_lookup={"WF-TEST-001": FIXTURE_PATH}, task_registrar=registrar)
    raw = engine.load("WF-TEST-001")

    engine.execute(raw, {})

    steps = [r.step for r in engine.lineage_tracer.list_records()]
    assert steps == ["collect", "extract", "rollback:collect"]
