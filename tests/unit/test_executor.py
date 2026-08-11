"""Unit tests for TaskExecutor (task execution contract + retry policy
enforcement).

TaskExecutionResult shape locked by 05_Interface_Contract.md section
5.2 / 12_Data_Contract.md section 4.2: task_name, status, duration_ms,
error. Output payload propagation goes through the executor's optional
`outputs` side-channel, not through the result object. Handler lookup
goes through `TaskRegistry.get_task()`, which returns `dict | None`
(section 4.6) — a dict-registered task's convention here is a "name"
key plus a callable "handler" key.
"""

from __future__ import annotations

from typing import Any

from core.context import ExecutionContext, ExecutionContextFactory
from core.executor import TaskExecutor
from core.models import TaskStatus
from core.registry import TaskRegistry
from core.workflow import RetryPolicy, TaskDefinition


def _context() -> ExecutionContext:
    return ExecutionContextFactory.create()


def test_execute_success_returns_success_result() -> None:
    registry = TaskRegistry()

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True, "execution_id": context.execution_id}

    registry.register({"name": "collect", "handler": handler})
    task = TaskDefinition(id="collect", type="adapter")
    executor = TaskExecutor(registry)
    context = _context()

    result = executor.execute(task, context)

    assert result.status is TaskStatus.SUCCESS
    assert result.task_name == "collect"
    assert result.duration_ms is not None
    assert result.error is None


def test_execute_returns_failure_when_task_not_registered() -> None:
    registry = TaskRegistry()
    task = TaskDefinition(id="collect", type="adapter")
    executor = TaskExecutor(registry)

    result = executor.execute(task, _context())

    assert result.status is TaskStatus.FAILED
    assert result.error is not None
    assert "collect" in result.error


def test_execute_returns_failure_when_handler_not_callable() -> None:
    registry = TaskRegistry()
    registry.register({"name": "collect", "handler": "not_a_function"})
    task = TaskDefinition(id="collect", type="adapter")
    executor = TaskExecutor(registry)

    result = executor.execute(task, _context())

    assert result.status is TaskStatus.FAILED
    assert result.error is not None


def test_execute_writes_output_to_outputs_side_channel() -> None:
    registry = TaskRegistry()

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True, "execution_id": context.execution_id}

    registry.register({"name": "collect", "handler": handler})
    task = TaskDefinition(id="collect", type="adapter")
    executor = TaskExecutor(registry)
    context = _context()
    outputs: dict[str, Any] = {}

    executor.execute(task, context, outputs=outputs)

    assert outputs["collect"] == {"ok": True, "execution_id": context.execution_id}


def test_execute_does_not_write_output_on_failure() -> None:
    registry = TaskRegistry()

    def always_fails(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("boom")

    registry.register({"name": "collect", "handler": always_fails})
    task = TaskDefinition(id="collect", type="adapter")
    executor = TaskExecutor(registry)
    outputs: dict[str, Any] = {}

    executor.execute(task, _context(), outputs=outputs)

    assert "collect" not in outputs


def test_execute_retries_on_failure_and_succeeds() -> None:
    registry = TaskRegistry()
    attempts: list[int] = []

    def flaky_handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("transient failure")
        return {"ok": True}

    registry.register({"name": "collect", "handler": flaky_handler})
    task = TaskDefinition(
        id="collect",
        type="adapter",
        retry_policy=RetryPolicy(strategy="exponential_backoff", max_attempts=3, base_delay_ms=0),
    )
    executor = TaskExecutor(registry)

    result = executor.execute(task, _context())

    assert result.status is TaskStatus.SUCCESS
    assert len(attempts) == 2


def test_execute_exhausts_retries_and_returns_failure_result() -> None:
    registry = TaskRegistry()
    attempts: list[int] = []

    def always_fails(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        attempts.append(1)
        raise RuntimeError("permanent failure")

    registry.register({"name": "collect", "handler": always_fails})
    task = TaskDefinition(
        id="collect",
        type="adapter",
        retry_policy=RetryPolicy(max_attempts=3, base_delay_ms=0),
    )
    executor = TaskExecutor(registry)

    result = executor.execute(task, _context())

    assert result.status is TaskStatus.FAILED
    assert result.error is not None
    assert "permanent failure" in result.error
    assert len(attempts) == 3


def test_execute_passes_task_input_to_handler() -> None:
    registry = TaskRegistry()
    seen_inputs: list[dict[str, Any]] = []

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        seen_inputs.append(task_input)
        return {}

    registry.register({"name": "collect", "handler": handler})
    task = TaskDefinition(id="collect", type="adapter", input={"product_id": "P123"})
    executor = TaskExecutor(registry)

    executor.execute(task, _context())

    assert seen_inputs == [{"product_id": "P123"}]


def test_execute_resolves_task_output_template() -> None:
    registry = TaskRegistry()
    seen_inputs: list[dict[str, Any]] = []

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        seen_inputs.append(task_input)
        return {}

    registry.register({"name": "extract", "handler": handler})
    task = TaskDefinition(
        id="extract", type="prompt", input={"raw_payload": "${collect.output}"}
    )
    executor = TaskExecutor(registry)
    outputs: dict[str, Any] = {"collect": {"price_text": "18500"}}

    executor.execute(task, _context(), outputs=outputs)

    assert seen_inputs == [{"raw_payload": {"price_text": "18500"}}]


def test_execute_resolves_bare_key_template_against_outputs() -> None:
    registry = TaskRegistry()
    seen_inputs: list[dict[str, Any]] = []

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        seen_inputs.append(task_input)
        return {}

    registry.register({"name": "collect", "handler": handler})
    task = TaskDefinition(id="collect", type="adapter", input={"product_id": "${product_id}"})
    executor = TaskExecutor(registry)
    outputs: dict[str, Any] = {"product_id": "P123"}

    executor.execute(task, _context(), outputs=outputs)

    assert seen_inputs == [{"product_id": "P123"}]


def test_execute_template_resolves_to_none_for_unknown_reference() -> None:
    registry = TaskRegistry()
    seen_inputs: list[dict[str, Any]] = []

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        seen_inputs.append(task_input)
        return {}

    registry.register({"name": "extract", "handler": handler})
    task = TaskDefinition(
        id="extract", type="prompt", input={"raw_payload": "${nonexistent.output}"}
    )
    executor = TaskExecutor(registry)

    executor.execute(task, _context(), outputs={})

    assert seen_inputs == [{"raw_payload": None}]


def test_execute_non_template_string_passes_through_unchanged() -> None:
    registry = TaskRegistry()
    seen_inputs: list[dict[str, Any]] = []

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        seen_inputs.append(task_input)
        return {}

    registry.register({"name": "collect", "handler": handler})
    task = TaskDefinition(
        id="collect", type="adapter", input={"note": "this mentions ${not_a_template} inline"}
    )
    executor = TaskExecutor(registry)

    executor.execute(task, _context(), outputs={})

    assert seen_inputs == [{"note": "this mentions ${not_a_template} inline"}]
