"""Unit tests for BootstrapKernel / BootstrapManager.

DoD reference (10_Project_Backlog.md, Sprint 1): "Bootstrap runs
successfully." BootstrapReport shape locked by
05_Interface_Contract.md section 5.3 / 12_Data_Contract.md section
4.3: execution_id, status, task_results, runtime_version,
kernel_version.
"""

from __future__ import annotations

from pathlib import Path

from core.bootstrap import BootstrapKernel, BootstrapManager
from core.models import BootstrapStatus, TaskStatus
from core.registry import TaskRegistry

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CONFIG_PATHS = [CONFIG_DIR / "runtime.yaml", CONFIG_DIR / "logging.yaml"]
TEST_ENV = {"HMIP_ENV": "test", "HMIP_LOG_LEVEL": "INFO"}


def _register_one_task(registry: TaskRegistry) -> None:
    registry.register({"name": "demo_task", "handler": lambda *_args: {}})


def test_bootstrap_succeeds_and_freezes_registry() -> None:
    kernel = BootstrapKernel(
        config_paths=CONFIG_PATHS,
        task_registrar=_register_one_task,
        env=TEST_ENV,
    )
    manager = BootstrapManager(kernel)

    report = manager.bootstrap()

    assert report.success is True
    assert report.status is BootstrapStatus.SUCCESS
    assert kernel.registry.state == "FROZEN"
    task_names = [t["name"] for t in kernel.registry.list_tasks()]
    assert "demo_task" in task_names
    assert kernel.context.execution_id
    assert kernel.config.fingerprint


def test_bootstrap_report_has_all_steps_in_order() -> None:
    kernel = BootstrapKernel(config_paths=CONFIG_PATHS, env=TEST_ENV)
    manager = BootstrapManager(kernel)

    report = manager.bootstrap()

    task_names = [r.task_name for r in report.task_results]
    assert task_names == [
        "load_environment",
        "resolve_config",
        "initialize_logging",
        "initialize_registry",
        "register_tasks",
        "freeze_registry",
        "build_context",
        "validate_runtime",
    ]
    assert all(r.status is TaskStatus.SUCCESS for r in report.task_results)
    assert all(r.duration_ms is not None for r in report.task_results)


def test_bootstrap_report_has_locked_version_fields() -> None:
    kernel = BootstrapKernel(config_paths=CONFIG_PATHS, env=TEST_ENV)
    manager = BootstrapManager(kernel)

    report = manager.bootstrap()

    assert report.runtime_version
    assert report.kernel_version


def test_bootstrap_fails_fast_on_missing_config() -> None:
    kernel = BootstrapKernel(
        config_paths=[CONFIG_DIR / "does_not_exist.yaml"],
        env=TEST_ENV,
    )
    manager = BootstrapManager(kernel)

    report = manager.bootstrap()

    assert report.success is False
    assert report.status is BootstrapStatus.FAILED
    failed_steps = [r for r in report.task_results if r.status is TaskStatus.FAILED]
    assert len(failed_steps) == 1
    assert failed_steps[0].task_name == "resolve_config"
    assert failed_steps[0].error is not None


def test_bootstrap_fails_fast_on_empty_config_paths() -> None:
    kernel = BootstrapKernel(config_paths=[], env=TEST_ENV)
    manager = BootstrapManager(kernel)

    report = manager.bootstrap()

    assert report.success is False
    assert report.task_results[0].task_name == "load_environment"
    assert report.task_results[0].status is TaskStatus.FAILED
