"""Chaos test: disk full (08_Testing_Standard.md section 11).

Simulates `PersistentLineageTracer`'s file write failing because the
underlying disk is full (`OSError: No space left on device`). Found
and fixed a real gap while writing this: `WorkflowEngine.execute()`
previously called `lineage_tracer.record_trace()` unguarded — a write
failure would have propagated as a raw `OSError` out of `execute()`
instead of the locked `WorkflowExecutionException`, and would not have
been distinguishable from an ordinary task business failure. Expected
per section 11: fail fast, error recorded via the locked exception
taxonomy, no corrupted state (the registry still reaches a terminal
state).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.context import ExecutionContext
from core.exceptions import WorkflowExecutionException
from core.lineage import PersistentLineageTracer
from core.registry import TaskRegistry
from core.workflow_engine import WorkflowEngine

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "integration"
    / "fixtures"
    / "generic_linear_workflow.yaml"
)


def _noop_registrar(registry: TaskRegistry) -> None:
    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"ok": True}

    for name in ("collect", "extract", "validate", "compare", "decide", "alert"):
        registry.register({"name": name, "handler": handler})


def test_disk_full_during_lineage_write_raises_locked_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracer = PersistentLineageTracer(tmp_path / "lineage.jsonl")
    engine = WorkflowEngine(
        workflow_lookup={"WF-TEST-001": FIXTURE_PATH},
        task_registrar=_noop_registrar,
        lineage_tracer=tracer,
    )
    workflow = engine.load("WF-TEST-001")  # reads the file BEFORE the disk fails

    def full_disk_open(self: Path, *args: object, **kwargs: object) -> object:
        raise OSError("No space left on device")

    monkeypatch.setattr(Path, "open", full_disk_open)

    with pytest.raises(WorkflowExecutionException) as exc_info:
        engine.execute(workflow, {})

    assert exc_info.value.code == "WORKFLOW_ENGINE_LINEAGE_WRITE_FAILED"


def test_disk_full_does_not_leak_raw_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracer = PersistentLineageTracer(tmp_path / "lineage.jsonl")
    engine = WorkflowEngine(
        workflow_lookup={"WF-TEST-001": FIXTURE_PATH},
        task_registrar=_noop_registrar,
        lineage_tracer=tracer,
    )
    workflow = engine.load("WF-TEST-001")  # reads the file BEFORE the disk fails

    def full_disk_open(self: Path, *args: object, **kwargs: object) -> object:
        raise OSError("No space left on device")

    monkeypatch.setattr(Path, "open", full_disk_open)

    try:
        engine.execute(workflow, {})
        pytest.fail("expected WorkflowExecutionException to be raised")
    except WorkflowExecutionException:
        pass  # expected — the taxonomy held
    except OSError:
        pytest.fail("raw OSError leaked past WorkflowEngine's boundary")
