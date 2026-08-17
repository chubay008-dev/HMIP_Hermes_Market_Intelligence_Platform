"""BootstrapKernel / BootstrapManager: the single entrypoint that
prepares the HMIP runtime before any workflow execution.

Bootstrap order (02_Runtime_Specification.md section 7):
    1. Load environment.
    2. Resolve base config.
    3. Initialize logging.
    4. Initialize container.
    5. Initialize registry.
    6. Register tasks and plugins.
    7. Freeze registry.
    8. Build runtime context.
    9. Validate runtime.
    10. Emit bootstrap report.

Sprint 1 scope: step 4 ("initialize container") has no DI framework
yet (see SPRINT_1_STATUS.md Assumptions) and is folded into registry
construction, which already happens via dependency injection in
`BootstrapKernel.__init__`.

Interface-contract retrofit (see SPRINT_3 status notes): each
bootstrap step produces a `core.models.TaskExecutionResult` — the same
shared result type used for workflow tasks — per the locked
`BootstrapReport` shape in 05_Interface_Contract.md section 5.3.
`_resolve_config` now drives `ConfigLoader`'s explicit
load -> validate -> freeze sequence (section 4.7), and
`_register_tasks`/`_freeze_registry` use `TaskRegistry`'s dict-based
`register()` / string `state` (section 4.6).
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from core.config import ConfigLoader, FrozenConfig
from core.context import ExecutionContext, ExecutionContextFactory
from core.exceptions import BootstrapError
from core.models import BootstrapReport, BootstrapStatus, TaskExecutionResult, TaskStatus
from core.observability import configure_logging, get_logger, log_event
from core.registry import TaskRegistry

TaskRegistrar = Callable[[TaskRegistry], None]


class BootstrapKernel:
    """Runs the fixed bootstrap sequence and produces a BootstrapReport.

    BootstrapKernel is the only component permitted to prepare the
    runtime before execution (01_System_Specification.md section 6:
    "bootstrap phải là bước duy nhất có quyền chuẩn bị runtime trước
    execution").
    """

    def __init__(
        self,
        *,
        config_paths: list[Path],
        task_registrar: TaskRegistrar | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._config_paths = config_paths
        self._task_registrar = task_registrar
        self._env = env if env is not None else dict(os.environ)
        self._registry = TaskRegistry()
        self._config: FrozenConfig | None = None
        self._context: ExecutionContext | None = None

    @property
    def registry(self) -> TaskRegistry:
        return self._registry

    @property
    def config(self) -> FrozenConfig:
        if self._config is None:
            raise BootstrapError(
                "bootstrap has not completed", code="BOOTSTRAP_NOT_COMPLETE"
            )
        return self._config

    @property
    def context(self) -> ExecutionContext:
        if self._context is None:
            raise BootstrapError(
                "bootstrap has not completed", code="BOOTSTRAP_NOT_COMPLETE"
            )
        return self._context

    def run(self) -> BootstrapReport:
        execution_id = str(uuid.uuid4())

        step_sequence: list[tuple[str, Callable[[], None]]] = [
            ("load_environment", self._load_environment),
            ("resolve_config", self._resolve_config),
            ("initialize_logging", self._initialize_logging),
            ("initialize_registry", self._initialize_registry),
            ("register_tasks", self._register_tasks),
            ("freeze_registry", self._freeze_registry),
            ("build_context", self._build_context),
            ("validate_runtime", self._validate_runtime),
        ]

        task_results: list[TaskExecutionResult] = []
        overall_status = BootstrapStatus.SUCCESS
        for name, fn in step_sequence:
            result = self._run_step(name, fn)
            task_results.append(result)
            if result.status is not TaskStatus.SUCCESS:
                overall_status = BootstrapStatus.FAILED
                break

        return BootstrapReport(
            execution_id=execution_id,
            status=overall_status,
            task_results=tuple(task_results),
        )

    def _run_step(self, name: str, fn: Callable[[], None]) -> TaskExecutionResult:
        """Run one bootstrap step and always return a result — never
        raises. A failing step is recorded as FAILED in the report
        instead of aborting the sequence via exception, so the report
        always reflects exactly which step failed (fail fast, but with
        full observability of the failure point)."""
        start = time.perf_counter()
        try:
            fn()
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return TaskExecutionResult(
                task_name=name,
                status=TaskStatus.FAILED,
                duration_ms=duration_ms,
                error=str(exc),
            )
        duration_ms = (time.perf_counter() - start) * 1000
        return TaskExecutionResult(
            task_name=name,
            status=TaskStatus.SUCCESS,
            duration_ms=duration_ms,
        )

    def _load_environment(self) -> None:
        if not self._config_paths:
            raise BootstrapError(
                "no config paths provided", code="BOOTSTRAP_NO_CONFIG_PATHS"
            )

    def _resolve_config(self) -> None:
        loader = ConfigLoader(self._config_paths, env=self._env)
        raw = loader.load()
        loader.validate(raw)
        self._config = loader.freeze(raw)

    def _initialize_logging(self) -> None:
        # Wire config/logging.yaml's `redact_fields` into structlog so the
        # declaration is actually enforced (it was previously inert — see
        # AGENTS.md security note). Falls back to the env/default set in
        # observability._parse_redact_fields when the config omits it.
        redact_fields = None
        if self._config is not None:
            logging_cfg = self._config.get("logging")
            if isinstance(logging_cfg, dict):
                fields = logging_cfg.get("redact_fields")
                if isinstance(fields, list):
                    redact_fields = fields
        configure_logging(redact_fields=redact_fields)

    def _initialize_registry(self) -> None:
        # Registry instance is created via constructor injection in
        # __init__; this step keeps the bootstrap order explicit and
        # independently testable, per spec section 7.
        pass

    def _register_tasks(self) -> None:
        if self._task_registrar is not None:
            self._task_registrar(self._registry)

    def _freeze_registry(self) -> None:
        self._registry.freeze()

    def _build_context(self) -> None:
        self._context = ExecutionContextFactory.create()

    def _validate_runtime(self) -> None:
        if self._config is None or self._context is None:
            raise BootstrapError(
                "runtime validation failed: missing config or context",
                code="BOOTSTRAP_VALIDATION_FAILED",
            )


class BootstrapManager:
    """Thin façade over BootstrapKernel used by CLI/platform entrypoints."""

    def __init__(self, kernel: BootstrapKernel) -> None:
        self._kernel = kernel

    def bootstrap(self) -> BootstrapReport:
        start = time.perf_counter()
        report = self._kernel.run()
        duration_ms = (time.perf_counter() - start) * 1000

        logger = get_logger("bootstrap")
        log_event(
            logger,
            event_type="bootstrap_completed" if report.success else "bootstrap_failed",
            status=report.status.value,
            execution_id=self._kernel.context.execution_id if report.success else None,
            duration_ms=duration_ms,
        )
        return report
