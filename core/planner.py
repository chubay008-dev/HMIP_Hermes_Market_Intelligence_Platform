"""Planner: builds a directed acyclic execution plan from a workflow
definition.

Contract locked by 05_Interface_Contract.md section 4.4: `plan()` and
`detect_cycles()` operate on `dict[str, Any]` in/out, not on the typed
`core.workflow.WorkflowDefinition` dataclass. Internally, both methods
parse the dict via `core.workflow.WorkflowLoader.loads()` to reuse
already-tested structural validation (unique task ids, known
dependencies, allowed types), then run a Kahn's-algorithm-style wave
builder over the typed result. `WorkflowDefinition`/`TaskDefinition`
remain the module's internal working representation — they are not
part of `Planner`'s public surface.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import WorkflowParseException
from core.workflow import WorkflowDefinition, WorkflowLoader


def _build_waves(workflow: WorkflowDefinition) -> tuple[tuple[str, ...], ...]:
    """Kahn's-algorithm-style wave builder: tasks within a wave have no
    dependency on each other and may run in parallel; waves execute in
    sequence. Task ids within a wave are sorted for deterministic,
    testable output. Raises `WorkflowParseException` (code
    `PLANNER_CYCLE_DETECTED`) on any dependency cycle, including
    self-cycles — the exact locked class, per project decision, not a
    finer-grained subclass."""
    remaining: dict[str, set[str]] = {task.id: set(task.dependencies) for task in workflow.tasks}
    waves: list[tuple[str, ...]] = []
    scheduled: set[str] = set()

    while remaining:
        ready = sorted(task_id for task_id, deps in remaining.items() if deps <= scheduled)
        if not ready:
            cyclic = sorted(remaining.keys())
            raise WorkflowParseException(
                f"workflow '{workflow.id}' has a dependency cycle involving "
                f"tasks: {cyclic}",
                code="PLANNER_CYCLE_DETECTED",
            )
        waves.append(tuple(ready))
        scheduled.update(ready)
        for task_id in ready:
            del remaining[task_id]

    return tuple(waves)


class Planner:
    """Stateless DAG planner conforming to 05_Interface_Contract.md
    section 4.4's `Planner` protocol. One instance may plan any number
    of workflows; it holds no per-workflow state between calls."""

    def plan(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Fail-fast: raises `WorkflowParseException` (code
        `PLANNER_CYCLE_DETECTED`) if `workflow` has a dependency cycle,
        rather than returning a partial or invalid plan."""
        parsed = WorkflowLoader().loads(workflow)
        waves = _build_waves(parsed)
        return {
            "workflow_id": parsed.id,
            "waves": [list(wave) for wave in waves],
        }

    def detect_cycles(self, workflow: dict[str, Any]) -> bool:
        """Pure query: returns True/False, never raises for a cycle
        (structural parse errors unrelated to cycles, e.g. an unknown
        dependency id, still propagate as `WorkflowParseException`)."""
        parsed = WorkflowLoader().loads(workflow)
        try:
            _build_waves(parsed)
        except WorkflowParseException:
            return True
        return False
