"""TaskRegistry: dict-based registry for tasks, skills, and plugins
registered before workflow execution begins.

Contract locked by 05_Interface_Contract.md section 4.6: `register()`
takes a plain `dict[str, Any]` describing the task. This codebase's
convention is that the dict must contain a non-empty string "name" key
and, for tasks meant to be executed by `core.executor.TaskExecutor`, a
callable "handler" key — the Protocol itself only requires
`dict[str, Any]`, so this is an implementation convention layered on
top, not an extra contract field. `get_task()` returns `None` for a
missing task rather than raising (per section 4.6's explicit rule).
`list_tasks()` returns a safe snapshot list of copies. `state` is a
plain `str` (backed internally by the `RegistryState` StrEnum for
internal type safety). `transition_to()` is the generic state-machine
entrypoint; `freeze()` remains a dedicated method since the contract
lists it separately from `transition_to()`.
"""

from __future__ import annotations

import threading
from enum import StrEnum
from typing import Any

from core.exceptions import RegistryStateException


class RegistryState(StrEnum):
    """TaskRegistry lifecycle states, per 02_Runtime_Specification.md
    section 6."""

    READY = "READY"
    FROZEN = "FROZEN"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


_ALLOWED_TRANSITIONS: dict[RegistryState, frozenset[RegistryState]] = {
    RegistryState.READY: frozenset({RegistryState.FROZEN}),
    RegistryState.FROZEN: frozenset({RegistryState.EXECUTING}),
    RegistryState.EXECUTING: frozenset({RegistryState.COMPLETED, RegistryState.FAILED}),
    RegistryState.COMPLETED: frozenset(),
    RegistryState.FAILED: frozenset(),
}


class TaskRegistry:
    """Thread-safe registry conforming to 05_Interface_Contract.md
    section 4.6's `Registry` protocol.

    Lifecycle: READY -> FROZEN -> EXECUTING -> {COMPLETED, FAILED}.
    Registration is only permitted while in READY.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: RegistryState = RegistryState.READY
        self._tasks: dict[str, dict[str, Any]] = {}

    @property
    def state(self) -> str:
        with self._lock:
            return self._state.value

    def register(self, task: dict[str, Any]) -> None:
        with self._lock:
            if self._state is not RegistryState.READY:
                raise RegistryStateException(
                    "cannot register a task while registry state is "
                    f"{self._state.value}",
                    code="REGISTRY_NOT_READY",
                )
            name = task.get("name")
            if not isinstance(name, str) or not name:
                raise RegistryStateException(
                    "task dict must contain a non-empty string 'name' key",
                    code="REGISTRY_INVALID_TASK_SCHEMA",
                )
            if name in self._tasks:
                raise RegistryStateException(
                    f"task '{name}' is already registered",
                    code="REGISTRY_DUPLICATE_TASK",
                )
            self._tasks[name] = dict(task)

    def get_task(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(name)
            return dict(task) if task is not None else None

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(task) for task in self._tasks.values()]

    def freeze(self) -> None:
        self.transition_to(RegistryState.FROZEN.value)

    def transition_to(self, state: str) -> None:
        with self._lock:
            try:
                target = RegistryState(state)
            except ValueError as exc:
                raise RegistryStateException(
                    f"'{state}' is not a known registry state",
                    code="REGISTRY_UNKNOWN_STATE",
                ) from exc
            allowed = _ALLOWED_TRANSITIONS[self._state]
            if target not in allowed:
                raise RegistryStateException(
                    f"invalid registry transition {self._state.value} -> "
                    f"{target.value}",
                    code="REGISTRY_INVALID_TRANSITION",
                )
            self._state = target
