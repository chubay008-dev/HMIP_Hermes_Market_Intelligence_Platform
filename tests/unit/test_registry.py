"""Unit tests for TaskRegistry, conforming to
05_Interface_Contract.md section 4.6's dict-based `Registry` protocol.

All registry errors raise the exact locked `RegistryStateException`
class (per project decision — no finer-grained subclasses); specific
failures are distinguished via `.code`.
"""

from __future__ import annotations

import pytest

from core.exceptions import RegistryStateException
from core.registry import TaskRegistry


def _noop(*_args: object) -> dict[str, object]:
    return {}


def test_initial_state_is_ready() -> None:
    registry = TaskRegistry()
    assert registry.state == "READY"


def test_register_task_while_ready() -> None:
    registry = TaskRegistry()
    registry.register({"name": "collect_price", "handler": _noop})

    names = [t["name"] for t in registry.list_tasks()]
    assert names == ["collect_price"]


def test_register_rejects_task_without_name() -> None:
    registry = TaskRegistry()

    with pytest.raises(RegistryStateException) as exc_info:
        registry.register({"handler": _noop})

    assert exc_info.value.code == "REGISTRY_INVALID_TASK_SCHEMA"


def test_register_rejects_task_with_empty_name() -> None:
    registry = TaskRegistry()

    with pytest.raises(RegistryStateException) as exc_info:
        registry.register({"name": "", "handler": _noop})

    assert exc_info.value.code == "REGISTRY_INVALID_TASK_SCHEMA"


def test_register_duplicate_task_raises() -> None:
    registry = TaskRegistry()
    registry.register({"name": "collect_price", "handler": _noop})

    with pytest.raises(RegistryStateException) as exc_info:
        registry.register({"name": "collect_price", "handler": _noop})

    assert exc_info.value.code == "REGISTRY_DUPLICATE_TASK"


def test_get_task_returns_matching_dict() -> None:
    registry = TaskRegistry()
    registry.register({"name": "collect_price", "handler": _noop, "kind": "adapter"})

    task = registry.get_task("collect_price")

    assert task is not None
    assert task["name"] == "collect_price"
    assert task["kind"] == "adapter"


def test_get_task_returns_none_for_missing_task() -> None:
    registry = TaskRegistry()

    assert registry.get_task("missing") is None


def test_get_task_returns_a_safe_copy() -> None:
    registry = TaskRegistry()
    registry.register({"name": "collect_price", "handler": _noop})

    snapshot = registry.get_task("collect_price")
    assert snapshot is not None
    snapshot["name"] = "mutated"

    unchanged = registry.get_task("collect_price")
    assert unchanged is not None
    assert unchanged["name"] == "collect_price"


def test_register_after_freeze_raises() -> None:
    registry = TaskRegistry()
    registry.freeze()

    with pytest.raises(RegistryStateException) as exc_info:
        registry.register({"name": "collect_price", "handler": _noop})

    assert exc_info.value.code == "REGISTRY_NOT_READY"


def test_full_lifecycle_transitions() -> None:
    registry = TaskRegistry()
    registry.register({"name": "collect_price", "handler": _noop})

    registry.freeze()
    assert registry.state == "FROZEN"

    registry.transition_to("EXECUTING")
    assert registry.state == "EXECUTING"

    registry.transition_to("COMPLETED")
    assert registry.state == "COMPLETED"


def test_failed_execution_transition() -> None:
    registry = TaskRegistry()
    registry.freeze()
    registry.transition_to("EXECUTING")

    registry.transition_to("FAILED")
    assert registry.state == "FAILED"


def test_invalid_transition_from_completed_raises() -> None:
    registry = TaskRegistry()
    registry.freeze()
    registry.transition_to("EXECUTING")
    registry.transition_to("COMPLETED")

    with pytest.raises(RegistryStateException) as exc_info:
        registry.freeze()

    assert exc_info.value.code == "REGISTRY_INVALID_TRANSITION"


def test_invalid_transition_skip_freeze_raises() -> None:
    registry = TaskRegistry()

    with pytest.raises(RegistryStateException) as exc_info:
        registry.transition_to("EXECUTING")

    assert exc_info.value.code == "REGISTRY_INVALID_TRANSITION"


def test_transition_to_unknown_state_raises() -> None:
    registry = TaskRegistry()

    with pytest.raises(RegistryStateException) as exc_info:
        registry.transition_to("NOT_A_REAL_STATE")

    assert exc_info.value.code == "REGISTRY_UNKNOWN_STATE"
