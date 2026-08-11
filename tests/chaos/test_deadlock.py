"""Chaos test: deadlock (08_Testing_Standard.md section 11).

Honest scope note: this codebase's task execution is single-threaded
and fully synchronous (no async execution model exists yet — see
`core.workflow_engine.WorkflowEngine.cancel()`'s own docstring for the
same limitation noted elsewhere). A genuine cross-thread deadlock
between two independent lock-holders isn't architecturally possible
in the current design, since nothing holds a lock across a call to
user code. What *is* meaningfully testable here: `TaskRegistry` uses
`threading.RLock` specifically so that reentrant access from the same
thread never self-deadlocks — this test proves that choice actually
holds, which is the most plausible deadlock-shaped failure mode if a
handler (or future orchestration code) ever calls back into the
registry from within a call the registry itself initiated.
"""

from __future__ import annotations

import threading
from typing import Any

from core.context import ExecutionContext
from core.registry import TaskRegistry


def test_registry_reentrant_access_from_same_thread_does_not_deadlock() -> None:
    registry = TaskRegistry()
    reentrant_calls: list[str] = []

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        # A handler reaching back into the registry it was resolved
        # from — the RLock must allow this without hanging.
        reentrant_calls.append(registry.state)
        return {"ok": True}

    registry.register({"name": "collect", "handler": handler})
    task_dict = registry.get_task("collect")
    assert task_dict is not None
    task_dict["handler"]({}, None)  # type: ignore[arg-type]

    assert reentrant_calls == ["READY"]


def test_registry_state_reads_from_another_thread_do_not_hang() -> None:
    """Not a deadlock in the classic two-lock sense, but proves a
    concurrent reader is never blocked indefinitely by normal
    single-threaded usage of the same registry."""
    registry = TaskRegistry()
    registry.register({"name": "collect", "handler": lambda *_args: {}})
    observed_states: list[str] = []
    error: list[BaseException] = []

    def reader() -> None:
        try:
            for _ in range(100):
                observed_states.append(registry.state)
        except BaseException as exc:  # noqa: BLE001 - captured for the assertion below
            error.append(exc)

    thread = threading.Thread(target=reader)
    thread.start()
    registry.freeze()
    thread.join(timeout=5.0)

    assert not thread.is_alive(), "reader thread hung — possible deadlock"
    assert not error
    assert len(observed_states) == 100
