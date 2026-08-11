"""Chaos test: network/external-API timeout (08_Testing_Standard.md
section 11).

No real HTTP adapter exists yet in this codebase (Sprint 3's
`CollectPriceAdapter` is a mock — see SPRINT_3_PRC001_STATUS.md), so
this simulates a timeout at the one seam that stands in for "a task
handler calling something external and slow": a `TaskHandler` that
raises `TimeoutError`. Expected per section 11: fail fast (after
exhausting the declared retry policy, not hang), error recorded,
system left in a clean, non-corrupted state (registry reaches a
terminal state; the whole run reports FAILED rather than crashing).
"""

from __future__ import annotations

from typing import Any

from core.context import ExecutionContext, ExecutionContextFactory
from core.executor import TaskExecutor
from core.models import TaskStatus
from core.registry import TaskRegistry
from core.workflow import RetryPolicy, TaskDefinition


def test_timeout_exhausts_retries_and_reports_failure_without_hanging() -> None:
    registry = TaskRegistry()
    attempts: list[int] = []

    def always_times_out(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        attempts.append(1)
        raise TimeoutError("simulated network timeout after 30s")

    registry.register({"name": "collect", "handler": always_times_out})
    task = TaskDefinition(
        id="collect",
        type="adapter",
        retry_policy=RetryPolicy(strategy="exponential_backoff", max_attempts=3, base_delay_ms=0),
    )
    executor = TaskExecutor(registry)

    result = executor.execute(task, ExecutionContextFactory.create())

    assert result.status is TaskStatus.FAILED
    assert result.error is not None
    assert "timeout" in result.error.lower()
    # Fail fast within the declared policy — not one attempt, not
    # infinite retries.
    assert len(attempts) == 3


def test_timeout_recovers_if_a_later_retry_succeeds() -> None:
    registry = TaskRegistry()
    attempts: list[int] = []

    def times_out_once(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("simulated transient network timeout")
        return {"ok": True}

    registry.register({"name": "collect", "handler": times_out_once})
    task = TaskDefinition(
        id="collect",
        type="adapter",
        retry_policy=RetryPolicy(strategy="exponential_backoff", max_attempts=3, base_delay_ms=0),
    )
    executor = TaskExecutor(registry)

    result = executor.execute(task, ExecutionContextFactory.create())

    assert result.status is TaskStatus.SUCCESS
    assert len(attempts) == 2


def test_timeout_with_no_retry_policy_fails_after_a_single_attempt() -> None:
    registry = TaskRegistry()
    attempts: list[int] = []

    def always_times_out(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        attempts.append(1)
        raise TimeoutError("simulated network timeout")

    registry.register({"name": "collect", "handler": always_times_out})
    task = TaskDefinition(id="collect", type="adapter")  # default RetryPolicy: max_attempts=1
    executor = TaskExecutor(registry)

    result = executor.execute(task, ExecutionContextFactory.create())

    assert result.status is TaskStatus.FAILED
    assert len(attempts) == 1
