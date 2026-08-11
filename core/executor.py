"""Task execution contract and default executor.

Defines the calling convention every registered task handler must
follow (`TaskHandler`), and a default `TaskExecutor` that resolves
handlers via `TaskRegistry.get_task()` (which returns `dict[str, Any]
| None` per 05_Interface_Contract.md section 4.6 — no exception for a
missing task), resolves `task.input` template references against an
`outputs` accumulator, applies the task's `RetryPolicy`, and always
returns a `TaskExecutionResult`. It never raises for an ordinary task
failure — including a missing/malformed registration — mirroring the
"always return a result, never raise for an expected failure" design
already used in `core.bootstrap.BootstrapKernel._run_step`.

`TaskExecutionResult`'s shape is locked to `task_name`, `status`,
`duration_ms`, `error` (05_Interface_Contract.md section 5.2) — it
carries no `output` field. A task's actual return payload (needed to
feed downstream tasks in a DAG, per `TaskDefinition.output`'s
`"${task.output}"` templating in 12_Data_Contract.md section 5.2) is
written into the optional `outputs` mapping the caller supplies to
`execute()`, keyed by task id, rather than smuggled onto the locked
result object. That same `outputs` mapping is also read from: any
string value in `task.input` matching `"${<ref>}"` is resolved against
it before the handler is called — `"${collect.output}"` resolves to
`outputs["collect"]`, and a bare `"${product_id}"` resolves to
`outputs["product_id"]` (e.g. workflow-level input the caller seeded
`outputs` with before execution began).
"""

from __future__ import annotations

import re
import time
from typing import Any, Protocol

from core.context import ExecutionContext
from core.models import TaskExecutionResult, TaskStatus
from core.registry import TaskRegistry
from core.workflow import TaskDefinition

_TEMPLATE_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_.]*)\}$")


def _resolve_value(value: Any, outputs: dict[str, Any]) -> Any:
    """Resolve a single `task.input` value against `outputs`. A
    template string is one that is *entirely* `"${...}"` (not
    interpolated inside a larger string) — anything else, including
    non-template strings and non-string values, passes through
    unchanged."""
    if not isinstance(value, str):
        return value
    match = _TEMPLATE_PATTERN.match(value)
    if not match:
        return value
    ref = match.group(1)
    if ref.endswith(".output"):
        ref = ref[: -len(".output")]
    return outputs.get(ref)


def _resolve_input(task_input: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    return {key: _resolve_value(value, outputs) for key, value in task_input.items()}


class TaskHandler(Protocol):
    """Calling convention every registered task handler must satisfy:
    accepts the task's resolved input dict and the current
    ExecutionContext, returns a JSON-serializable output dict."""

    def __call__(
        self, task_input: dict[str, Any], context: ExecutionContext
    ) -> dict[str, Any]: ...


class TaskExecutor:
    """Executes a single TaskDefinition by resolving its handler from a
    TaskRegistry and applying the task's RetryPolicy.

    Retry is a simple fixed/linear-backoff loop keyed off
    `RetryPolicy.base_delay_ms * attempt` — sufficient for Sprint 2's
    "retry policy skeleton" scope. A real exponential-backoff strategy
    selector is deferred; `RetryPolicy.strategy` is stored but not yet
    interpreted differently per value.
    """

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        task: TaskDefinition,
        context: ExecutionContext,
        *,
        outputs: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        task_dict = self._registry.get_task(task.id)
        if task_dict is None:
            return TaskExecutionResult(
                task_name=task.id,
                status=TaskStatus.FAILED,
                duration_ms=0.0,
                error=f"no handler registered for task '{task.id}'",
            )

        handler = task_dict.get("handler")
        if not callable(handler):
            return TaskExecutionResult(
                task_name=task.id,
                status=TaskStatus.FAILED,
                duration_ms=0.0,
                error=f"registered task '{task.id}' has no callable 'handler'",
            )

        resolved_input = _resolve_input(task.input, outputs if outputs is not None else {})

        policy = task.retry_policy
        last_error: Exception | None = None
        overall_start = time.perf_counter()

        for attempt in range(1, policy.max_attempts + 1):
            try:
                output = handler(resolved_input, context)
            except Exception as exc:  # noqa: BLE001 - reported via TaskExecutionResult
                last_error = exc
                if attempt < policy.max_attempts and policy.base_delay_ms > 0:
                    time.sleep((policy.base_delay_ms / 1000) * attempt)
                continue

            duration_ms = (time.perf_counter() - overall_start) * 1000
            if outputs is not None:
                outputs[task.id] = output
            return TaskExecutionResult(
                task_name=task.id,
                status=TaskStatus.SUCCESS,
                duration_ms=duration_ms,
            )

        duration_ms = (time.perf_counter() - overall_start) * 1000
        return TaskExecutionResult(
            task_name=task.id,
            status=TaskStatus.FAILED,
            duration_ms=duration_ms,
            error=str(last_error) if last_error else "unknown error",
        )
