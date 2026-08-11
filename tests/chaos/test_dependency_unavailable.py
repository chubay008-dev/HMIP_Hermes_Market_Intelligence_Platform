"""Chaos test: dependency unavailable (08_Testing_Standard.md section
11).

Two flavors of "a dependency this workflow needs isn't there":
(1) an adapter's *external* source has no data for the requested key
(`CollectPriceAdapter`'s mock lookup miss — the real PRC-001 case,
already exercised end-to-end in
`tests/workflow/test_prc_001_end_to_end.py::test_prc_001_fails_gracefully_for_unknown_product`,
referenced here rather than duplicated), and (2) a task references a
handler that was never registered at all — a deployment/configuration
mistake rather than a data problem. Expected per section 11: fail
fast, error recorded, no corrupted state.
"""

from __future__ import annotations

from typing import Any

from core.context import ExecutionContext, ExecutionContextFactory
from core.executor import TaskExecutor
from core.models import TaskStatus
from core.registry import TaskRegistry
from core.workflow import TaskDefinition


def test_missing_handler_registration_fails_fast_without_raising() -> None:
    """A task references a handler name that nothing ever registered
    — e.g. a workflow YAML edit added a task without updating its
    registrar. Must be reported as an ordinary FAILED result (per
    TaskExecutor's "always return, never raise" design), not crash the
    caller."""
    registry = TaskRegistry()  # nothing registered at all
    task = TaskDefinition(id="collect", type="adapter")
    executor = TaskExecutor(registry)

    result = executor.execute(task, ExecutionContextFactory.create())

    assert result.status is TaskStatus.FAILED
    assert result.error is not None
    assert "collect" in result.error


def test_dependency_unavailable_does_not_prevent_other_registered_tasks() -> None:
    """One task's handler being unavailable must not corrupt the
    registry or block unrelated, properly-registered tasks from being
    resolved and executed independently."""
    registry = TaskRegistry()

    def healthy_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True}

    registry.register({"name": "extract", "handler": healthy_handler})
    executor = TaskExecutor(registry)

    missing_task = TaskDefinition(id="collect", type="adapter")
    healthy_task = TaskDefinition(id="extract", type="prompt")

    missing_result = executor.execute(missing_task, ExecutionContextFactory.create())
    healthy_result = executor.execute(healthy_task, ExecutionContextFactory.create())

    assert missing_result.status is TaskStatus.FAILED
    assert healthy_result.status is TaskStatus.SUCCESS


def test_handler_registered_with_non_callable_value_fails_fast() -> None:
    """A registration mistake — a "handler" key holding a non-callable
    value (e.g. accidentally registering a string or the result of
    calling a factory instead of the factory itself)."""
    registry = TaskRegistry()
    registry.register({"name": "collect", "handler": "not_actually_a_function"})
    task = TaskDefinition(id="collect", type="adapter")
    executor = TaskExecutor(registry)

    result = executor.execute(task, ExecutionContextFactory.create())

    assert result.status is TaskStatus.FAILED
    assert result.error is not None
