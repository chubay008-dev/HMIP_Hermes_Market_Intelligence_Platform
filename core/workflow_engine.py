"""WorkflowEngine: ties WorkflowLoader, Planner, TaskRegistry,
TaskExecutor, EventBus, and a LineageTracer together to run a workflow
end-to-end.

Contract locked by 05_Interface_Contract.md section 4.3:
`load(workflow_id) -> dict`, `execute(workflow: dict, context: dict)
-> dict`, `cancel(execution_id) -> None`. Per that section's rule
("WorkflowEngine không nên gánh trách nhiệm planning chi tiết nếu
Planner đã tồn tại"), all DAG planning is delegated to
`core.planner.Planner` — this class only sequences already-planned
waves and manages per-execution TaskRegistry lifecycle.

`execute()`'s `context: dict[str, Any]` parameter is interpreted as
the workflow's *business input* (e.g. `{"product_id": "P123",
"source": "shopee", "market": "VN"}`, per 12_Data_Contract.md section
4.4's `WorkflowExecutionRecord.input` example) — not a serialized
`core.context.ExecutionContext`. The engine creates its own
`ExecutionContext` internally for tracing. This is a documented
interpretation, since section 4.3 itself only says `dict[str, Any]`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from core.context import ExecutionContextFactory
from core.event_bus import EventBus
from core.exceptions import (
    EventDeliveryError,
    WorkflowExecutionException,
    WorkflowParseException,
)
from core.executor import TaskExecutor
from core.lineage import InMemoryLineageTracer, LineageTracer
from core.models import TaskStatus
from core.planner import Planner
from core.registry import TaskRegistry
from core.workflow import WorkflowLoader

TaskRegistrar = Callable[[TaskRegistry], None]


class WorkflowEngine:
    """Runs workflows end-to-end, conforming to
    05_Interface_Contract.md section 4.3's `WorkflowEngine` protocol.

    A fresh `TaskRegistry` is created and frozen for every `execute()`
    call (registries are single-lifecycle, per `core/registry.py`), so
    one `WorkflowEngine` instance can safely run many executions.
    """

    def __init__(
        self,
        *,
        workflow_lookup: dict[str, Path],
        task_registrar: TaskRegistrar,
        event_bus: EventBus | None = None,
        lineage_tracer: LineageTracer | None = None,
    ) -> None:
        self._workflow_lookup = workflow_lookup
        self._task_registrar = task_registrar
        self._event_bus = event_bus if event_bus is not None else EventBus()
        self._lineage_tracer: LineageTracer = (
            lineage_tracer if lineage_tracer is not None else InMemoryLineageTracer()
        )
        self._cancelled: set[str] = set()

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def lineage_tracer(self) -> LineageTracer:
        return self._lineage_tracer

    def load(self, workflow_id: str) -> dict[str, Any]:
        path = self._workflow_lookup.get(workflow_id)
        if path is None:
            raise WorkflowParseException(
                f"no workflow registered for id '{workflow_id}'",
                code="WORKFLOW_ENGINE_UNKNOWN_ID",
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise WorkflowParseException(
                f"workflow root must be a mapping: {path}",
                code="WORKFLOW_ENGINE_INVALID_ROOT",
            )
        if raw.get("id") != workflow_id:
            raise WorkflowParseException(
                f"workflow file at {path} declares id '{raw.get('id')}', "
                f"expected '{workflow_id}'",
                code="WORKFLOW_ENGINE_ID_MISMATCH",
            )
        return raw

    def execute(self, workflow: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Fail-fast on structural problems (`WorkflowParseException`
        from `WorkflowLoader`/`Planner`, propagated — a malformed
        workflow definition is a programmer/config error, not an
        ordinary runtime failure) or on infrastructure failures inside
        the run loop (`WorkflowExecutionException`, e.g. a broken
        event subscriber). Per-task business failures are NOT raised —
        they're reported via the returned dict's `status`/`error`
        fields, same as `TaskExecutionResult` already does per task."""
        execution_id = str(uuid.uuid4())
        exec_context = ExecutionContextFactory.create(metadata={"workflow_input": context})
        started_at = time.time()

        workflow_def = WorkflowLoader().loads(workflow)
        plan = Planner().plan(workflow)

        registry = TaskRegistry()
        self._task_registrar(registry)
        registry.freeze()
        registry.transition_to("EXECUTING")

        executor = TaskExecutor(registry)
        outputs: dict[str, Any] = dict(context)
        error: str | None = None
        status = "COMPLETED"
        executed_task_ids: list[str] = []

        flat_order = [task_id for wave in plan["waves"] for task_id in wave]
        for task_id in flat_order:
            if execution_id in self._cancelled:
                status = "CANCELLED"
                break

            task = workflow_def.get_task(task_id)
            result = executor.execute(task, exec_context, outputs=outputs)

            try:
                self._lineage_tracer.record_trace(
                    step_id=task_id,
                    input_val=task.input,
                    output_val=outputs.get(task_id),
                    model_info=f"task:{task_id}:{task.type}",
                )
            except Exception as exc:  # noqa: BLE001 - converted below, not swallowed
                # e.g. a PersistentLineageTracer write failing because
                # the underlying storage is full or unavailable. This
                # is an infrastructure failure, not a task business
                # failure, so it raises rather than being folded into
                # the returned dict's status/error fields.
                raise WorkflowExecutionException(
                    f"lineage recording failed for task '{task_id}': {exc}",
                    code="WORKFLOW_ENGINE_LINEAGE_WRITE_FAILED",
                ) from exc

            try:
                self._event_bus.publish(
                    {
                        "event_type": "task_completed",
                        "task_id": task_id,
                        "status": result.status.value,
                    }
                )
            except EventDeliveryError as exc:
                raise WorkflowExecutionException(
                    f"event delivery failed for task '{task_id}': {exc}",
                    code="WORKFLOW_ENGINE_EVENT_DELIVERY_FAILED",
                ) from exc

            if result.status is not TaskStatus.SUCCESS:
                status = "FAILED"
                error = result.error
                break

            executed_task_ids.append(task_id)

        compensation: dict[str, Any] = {"triggered": False, "completed": True, "errors": []}
        if status == "FAILED" and workflow_def.compensation_policy == "STRICT":
            compensation = self._compensate(
                registry=registry,
                executed_task_ids=executed_task_ids,
                outputs=outputs,
                execution_id=execution_id,
            )

        registry.transition_to("FAILED" if status == "FAILED" else "COMPLETED")
        self._cancelled.discard(execution_id)

        return {
            "execution_id": execution_id,
            "workflow_id": workflow_def.id,
            "status": status,
            "started_at": started_at,
            "ended_at": time.time(),
            "input": context,
            "output": outputs.get(flat_order[-1]) if flat_order and status == "COMPLETED" else None,
            "error": error,
            "trace_id": exec_context.trace_id,
            "compensation": compensation,
        }

    def _compensate(
        self,
        *,
        registry: TaskRegistry,
        executed_task_ids: list[str],
        outputs: dict[str, Any],
        execution_id: str,
    ) -> dict[str, Any]:
        """Calls each successfully-completed task's registered
        `"rollback"` callable (if any), in reverse execution order, per
        `WorkflowDefinition.compensation_policy == "STRICT"`
        (12_Data_Contract.md section 5.2). A task with no `"rollback"`
        key registered is skipped, not treated as an error — the
        `Registry` protocol's task dict has no mandatory keys beyond
        this codebase's own `"name"`/`"handler"` convention (see
        `core/registry.py`), and not every task type has anything
        meaningful to compensate (e.g. a `BaseAdapter`'s read-only
        `fetch()`).

        A single rollback failing does not stop the rest from being
        attempted — every task gets a compensation attempt, and every
        failure is collected rather than only the first. Lineage
        recording for a rollback step is best-effort: if it fails, the
        rollback itself (which already ran) is still counted as
        successful — losing an audit-trail entry must not be conflated
        with the compensating action itself failing.
        """
        errors: list[dict[str, Any]] = []
        for task_id in reversed(executed_task_ids):
            task_dict = registry.get_task(task_id)
            rollback = task_dict.get("rollback") if task_dict is not None else None
            if not callable(rollback):
                continue

            compensation_context = {
                "task_id": task_id,
                "output": outputs.get(task_id),
                "execution_id": execution_id,
            }
            try:
                rollback(compensation_context)
            except Exception as exc:  # noqa: BLE001 - collected, not swallowed
                errors.append({"task_id": task_id, "error": str(exc)})
                continue

            try:
                self._lineage_tracer.record_trace(
                    step_id=f"rollback:{task_id}",
                    input_val=compensation_context,
                    output_val=None,
                    model_info=f"compensation:{task_id}",
                )
            except Exception:  # noqa: BLE001 - best-effort audit trail only
                # Best-effort lineage recording - log warning if failed
                import logging
                logging.warning(
                    "Failed to record lineage trace for rollback step", exc_info=True
                )

        return {"triggered": True, "completed": not errors, "errors": errors}

    def cancel(self, execution_id: str) -> None:
        """Best-effort only: `execute()` is fully synchronous and
        generates `execution_id` internally, so a caller has no way to
        obtain it before `execute()` has already returned — genuine
        mid-flight cancellation requires an async/concurrent execution
        model that does not exist yet. This records the request and
        `execute()`'s per-task loop checks it between tasks, so it
        would take effect if `execute()` were ever called from another
        thread with a known `execution_id` (not currently possible
        through this class's own API)."""
        self._cancelled.add(execution_id)
