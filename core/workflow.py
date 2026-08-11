"""Workflow definition contracts.

Data shapes per 19_Example_Workflows.md / 20_Sample_Schemas.md section
5, plus a strict WorkflowLoader that parses a YAML workflow definition
into a WorkflowDefinition and validates its structural invariants
(unique task ids, dependencies referencing existing tasks, allowed
task types). DAG cycle detection is NOT done here — see
`core/planner.py::Planner`, which is the only component allowed to
reason about execution order.

All structural validation failures raise `WorkflowParseException` per
05_Interface_Contract.md section 6 ("Workflow parsing errors phải
raise WorkflowParseException").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.exceptions import WorkflowParseException

# Allowed TaskDefinition.type values (20_Sample_Schemas.md section 5.2).
ALLOWED_TASK_TYPES = frozenset(
    {"adapter", "prompt", "schema_validate", "decision", "notify", "transform", "persist"}
)


@dataclass(frozen=True)
class RetryPolicy:
    """Retry policy attached to a single task.

    `strategy` is currently either "none" or "exponential_backoff";
    actual backoff/sleep enforcement happens in the executor
    (`core/executor.py`), not here — this is a pure data contract.
    """

    strategy: str = "none"
    max_attempts: int = 1
    base_delay_ms: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise WorkflowParseException(
                "max_attempts must be >= 1", code="RETRY_POLICY_INVALID_ATTEMPTS"
            )
        if self.base_delay_ms < 0:
            raise WorkflowParseException(
                "base_delay_ms must be >= 0", code="RETRY_POLICY_INVALID_DELAY"
            )


@dataclass(frozen=True)
class TaskDefinition:
    """A single task node inside a WorkflowDefinition DAG."""

    id: str
    type: str
    input: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout: int | None = None
    failure_modes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.id:
            raise WorkflowParseException("task id must not be empty", code="TASK_MISSING_ID")
        if self.type not in ALLOWED_TASK_TYPES:
            raise WorkflowParseException(
                f"task '{self.id}' has invalid type '{self.type}'",
                code="TASK_INVALID_TYPE",
            )


@dataclass(frozen=True)
class WorkflowDefinition:
    """A parsed, structurally-validated workflow.

    Cycle detection is intentionally NOT performed in this constructor
    — only referential integrity (unique ids, known dependencies).
    Use `core.planner.Planner.plan()` to obtain a cycle-free execution
    order.
    """

    id: str
    version: str
    owner: str
    tasks: tuple[TaskDefinition, ...]
    status: str = "DRAFT"
    risk: str = "LOW"
    inputs: tuple[str, ...] = field(default_factory=tuple)
    outputs: tuple[str, ...] = field(default_factory=tuple)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    compensation_policy: str = "STRICT"
    schema_dependencies: tuple[str, ...] = field(default_factory=tuple)
    prompt_dependencies: tuple[str, ...] = field(default_factory=tuple)
    skill_dependencies: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.id:
            raise WorkflowParseException(
                "workflow id must not be empty", code="WORKFLOW_MISSING_ID"
            )
        if not self.tasks:
            raise WorkflowParseException(
                f"workflow '{self.id}' must declare at least one task",
                code="WORKFLOW_EMPTY_TASKS",
            )
        task_ids = [t.id for t in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise WorkflowParseException(
                f"workflow '{self.id}' has duplicate task ids",
                code="WORKFLOW_DUPLICATE_TASK_ID",
            )
        known_ids = set(task_ids)
        for task in self.tasks:
            for dep in task.dependencies:
                if dep not in known_ids:
                    raise WorkflowParseException(
                        f"workflow '{self.id}' task '{task.id}' depends on "
                        f"unknown task '{dep}'",
                        code="WORKFLOW_UNKNOWN_DEPENDENCY",
                    )

    def get_task(self, task_id: str) -> TaskDefinition:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise WorkflowParseException(
            f"task '{task_id}' not found in workflow '{self.id}'",
            code="WORKFLOW_TASK_NOT_FOUND",
        )


def _parse_retry_policy(raw: Any) -> RetryPolicy:
    if raw is None:
        return RetryPolicy()
    if isinstance(raw, str):
        return RetryPolicy(strategy=raw, max_attempts=3 if raw != "none" else 1)
    if isinstance(raw, dict):
        return RetryPolicy(
            strategy=raw.get("strategy", "none"),
            max_attempts=int(raw.get("max_attempts", 1)),
            base_delay_ms=float(raw.get("base_delay_ms", 0.0)),
        )
    raise WorkflowParseException(
        f"unsupported retry_policy shape: {type(raw)!r}",
        code="RETRY_POLICY_INVALID_SHAPE",
    )


def _parse_task(raw: dict[str, Any]) -> TaskDefinition:
    return TaskDefinition(
        id=raw.get("id", ""),
        type=raw.get("type", ""),
        input=dict(raw.get("input") or {}),
        output=raw.get("output"),
        dependencies=tuple(raw.get("dependencies") or ()),
        retry_policy=_parse_retry_policy(raw.get("retry_policy")),
        timeout=raw.get("timeout"),
        failure_modes=tuple(raw.get("failure_modes") or ()),
    )


class WorkflowLoader:
    """Loads a WorkflowDefinition from a YAML file or an already-parsed
    mapping. Stateless and reusable — may be called any number of
    times, on any number of workflows."""

    def load(self, path: Path) -> WorkflowDefinition:
        if not path.exists():
            raise WorkflowParseException(
                f"workflow file not found: {path}", code="WORKFLOW_FILE_NOT_FOUND"
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise WorkflowParseException(
                f"invalid yaml in {path}: {exc}", code="WORKFLOW_INVALID_YAML"
            ) from exc
        if not isinstance(raw, dict):
            raise WorkflowParseException(
                f"workflow root must be a mapping: {path}", code="WORKFLOW_INVALID_ROOT"
            )
        return self.loads(raw)

    def loads(self, raw: dict[str, Any]) -> WorkflowDefinition:
        tasks_raw = raw.get("tasks") or []
        tasks = tuple(_parse_task(t) for t in tasks_raw)
        return WorkflowDefinition(
            id=raw.get("id", ""),
            version=raw.get("version", ""),
            owner=raw.get("owner", ""),
            tasks=tasks,
            status=raw.get("status", "DRAFT"),
            risk=raw.get("risk", "LOW"),
            inputs=tuple(raw.get("inputs") or ()),
            outputs=tuple(raw.get("outputs") or ()),
            retry_policy=_parse_retry_policy(raw.get("retry_policy")),
            compensation_policy=raw.get("compensation_policy", "STRICT"),
            schema_dependencies=tuple(raw.get("schema_dependencies") or ()),
            prompt_dependencies=tuple(raw.get("prompt_dependencies") or ()),
            skill_dependencies=tuple(raw.get("skill_dependencies") or ()),
        )
