"""Unit tests for Planner, conforming to 05_Interface_Contract.md
section 4.4's dict-based `Planner` protocol (`plan()`/`detect_cycles()`
take and return `dict[str, Any]`, not the typed WorkflowDefinition).

All planning/parsing failures raise the exact locked
`WorkflowParseException` class (per project decision); cycle-specific
failures are distinguished via `.code == "PLANNER_CYCLE_DETECTED"`.
"""

from __future__ import annotations

import pytest

from core.exceptions import WorkflowParseException
from core.planner import Planner


def _task(task_id: str, deps: list[str] | None = None) -> dict[str, object]:
    return {"id": task_id, "type": "adapter", "dependencies": deps or []}


def _workflow(*tasks: dict[str, object]) -> dict[str, object]:
    return {"id": "WF-TEST", "version": "1.0.0", "owner": "team", "tasks": list(tasks)}


def test_plan_linear_chain_produces_one_task_per_wave() -> None:
    workflow = _workflow(
        _task("collect"),
        _task("extract", ["collect"]),
        _task("validate", ["extract"]),
    )

    plan = Planner().plan(workflow)

    assert plan["workflow_id"] == "WF-TEST"
    assert plan["waves"] == [["collect"], ["extract"], ["validate"]]


def test_plan_diamond_dependency_groups_parallel_tasks_in_one_wave() -> None:
    # A -> B, A -> C, {B, C} -> D
    workflow = _workflow(
        _task("a"),
        _task("b", ["a"]),
        _task("c", ["a"]),
        _task("d", ["b", "c"]),
    )

    plan = Planner().plan(workflow)

    assert plan["waves"] == [["a"], ["b", "c"], ["d"]]


def test_plan_independent_tasks_share_first_wave() -> None:
    workflow = _workflow(_task("collect"), _task("collect_2"))

    plan = Planner().plan(workflow)

    assert plan["waves"] == [["collect", "collect_2"]]


def test_plan_raises_planner_error_on_direct_cycle() -> None:
    # WorkflowLoader.loads() only validates referential integrity (every
    # dependency id must exist), not acyclicity — a 2-cycle where both
    # ids are known to each other parses fine and must be caught by the
    # planner instead.
    workflow = _workflow(_task("a", ["b"]), _task("b", ["a"]))

    with pytest.raises(WorkflowParseException) as exc_info:
        Planner().plan(workflow)

    assert exc_info.value.code == "PLANNER_CYCLE_DETECTED"


def test_plan_raises_planner_error_on_self_dependency() -> None:
    workflow = _workflow(_task("a", ["a"]))

    with pytest.raises(WorkflowParseException) as exc_info:
        Planner().plan(workflow)

    assert exc_info.value.code == "PLANNER_CYCLE_DETECTED"


def test_plan_raises_workflow_parse_exception_on_unknown_dependency() -> None:
    workflow = _workflow(_task("extract", ["collect"]))  # "collect" not declared

    with pytest.raises(WorkflowParseException):
        Planner().plan(workflow)


def test_detect_cycles_returns_true_for_cyclic_workflow() -> None:
    workflow = _workflow(_task("a", ["b"]), _task("b", ["a"]))

    assert Planner().detect_cycles(workflow) is True


def test_detect_cycles_returns_false_for_acyclic_workflow() -> None:
    workflow = _workflow(_task("collect"), _task("extract", ["collect"]))

    assert Planner().detect_cycles(workflow) is False


def test_detect_cycles_does_not_raise_for_cyclic_workflow() -> None:
    workflow = _workflow(_task("a", ["a"]))

    result = Planner().detect_cycles(workflow)  # must not raise

    assert result is True
