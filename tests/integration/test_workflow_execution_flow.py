"""Integration test: WorkflowLoader -> Planner -> TaskRegistry ->
TaskExecutor -> EventBus, wired together the way a future
orchestrator will compose them. There is no core/orchestrator.py yet
(deferred to a later sprint per 10_Project_Backlog.md); this test
proves the Sprint 2 building blocks work correctly together end-to-end
using the dict-based `Planner`/`Registry`/`EventBus` protocols locked
by 05_Interface_Contract.md section 4.

Modeled after the PRC-001 example flow in 19_Example_Workflows.md
(collect -> extract -> validate -> compare -> decide -> alert), using
generic no-op handlers — real domain logic is Sprint 3 scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.context import ExecutionContext, ExecutionContextFactory
from core.event_bus import EventBus
from core.executor import TaskExecutor
from core.planner import Planner
from core.registry import TaskRegistry
from core.workflow import WorkflowLoader

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "generic_linear_workflow.yaml"


def _make_handler(name: str, calls: list[str]) -> Any:
    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        calls.append(name)
        return {"step": name, "execution_id": context.execution_id}

    return handler


def test_full_flow_executes_all_tasks_in_dependency_order() -> None:
    # Planner takes/returns plain dicts (05_Interface_Contract.md
    # section 4.4) — read the raw YAML dict directly for it.
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    plan = Planner().plan(raw)

    # WorkflowLoader gives the typed, validated WorkflowDefinition used
    # for task lookups (get_task) and registering handlers.
    workflow = WorkflowLoader().load(FIXTURE_PATH)

    registry = TaskRegistry()
    calls: list[str] = []
    for task in workflow.tasks:
        registry.register({"name": task.id, "handler": _make_handler(task.id, calls)})
    registry.freeze()
    registry.transition_to("EXECUTING")

    bus = EventBus()
    published: list[dict[str, Any]] = []
    bus.subscribe("task_completed", published.append)

    executor = TaskExecutor(registry)
    context = ExecutionContextFactory.create()

    flat_order = [task_id for wave in plan["waves"] for task_id in wave]
    for task_id in flat_order:
        task = workflow.get_task(task_id)
        result = executor.execute(task, context)
        assert result.status.value == "SUCCESS"
        bus.publish({"event_type": "task_completed", "task_id": task_id})

    registry.transition_to("COMPLETED")

    assert calls == flat_order
    assert [e["task_id"] for e in published] == flat_order


def test_plan_matches_declared_linear_dependencies() -> None:
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    plan = Planner().plan(raw)

    flat_order = [task_id for wave in plan["waves"] for task_id in wave]
    assert flat_order == ["collect", "extract", "validate", "compare", "decide", "alert"]
