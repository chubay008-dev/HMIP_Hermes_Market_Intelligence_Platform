"""CLI entrypoint for HMIP bootstrap.

Usage:
    python -m platform_.bootstrap

NOTE: this package was named `platform/` through Sprint 6 (per
14_Repository_File_Mapping.md section 7 verbatim), then renamed to
`platform_/` after the collision with Python's standard library
`platform` module — flagged as a risk since Sprint 1 — broke pytest's
ability to collect any test importing from this package at all. See
ADR_010_platform_package_rename.md.

Sprint 6 additions (09_Deployment_Guide.md sections 7/8/11): writes
the full `BootstrapReport` to `HMIP_REPORT_DIR` (default `reports/`)
on every run — success or failure — so a failed bootstrap always
leaves "report đủ ngữ cảnh để debug" behind; and marks the process
ready (`platform_.readiness.mark_ready()`) only on success, for the
container healthcheck/readiness probe to observe.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

from core.bootstrap import BootstrapKernel, BootstrapManager
from core.models import BootstrapReport, TaskStatus
from core.registry import TaskRegistry
from platform_.readiness import mark_ready

DEFAULT_CONFIG_FILENAMES = ["runtime.yaml", "logging.yaml", "deployment.yaml"]
CONFIG_DIR_ENV_VAR = "HMIP_CONFIG_PATH"
REPORT_DIR_ENV_VAR = "HMIP_REPORT_DIR"


def _config_paths() -> list[Path]:
    """09_Deployment_Guide.md section 5 lists `HMIP_CONFIG_PATH` as a
    standard env var for overriding where config/*.yaml is read from;
    defaults to `./config` if unset."""
    config_dir = Path(os.environ.get(CONFIG_DIR_ENV_VAR) or "config")
    return [config_dir / name for name in DEFAULT_CONFIG_FILENAMES]


def _register_demo_tasks(registry: TaskRegistry) -> None:
    """Sprint 1 placeholder registrar. Real task registration for
    PRC-001 arrives in Sprint 3 (03_Domain_Specification.md section 6).
    `register()` takes a plain dict per 05_Interface_Contract.md
    section 4.6 — this codebase's convention is a "name" key plus a
    callable "handler" key."""
    registry.register({"name": "noop", "handler": lambda *_args: {}, "kind": "placeholder"})


def _reports_dir() -> Path:
    override = os.environ.get(REPORT_DIR_ENV_VAR)
    return Path(override) if override else Path("reports")


def _write_bootstrap_report(report: BootstrapReport, reports_dir: Path) -> Path:
    """Persists the full report as JSON — every field, including each
    step's `error` message — not just the summary printed to stdout.
    `BootstrapStatus`/`TaskStatus` are `StrEnum` members, so they
    serialize natively via `json.dumps` without a custom encoder."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"bootstrap_{report.execution_id}.json"
    report_path.write_text(
        json.dumps(dataclasses.asdict(report), indent=2, default=str),
        encoding="utf-8",
    )
    return report_path


def main() -> int:
    kernel = BootstrapKernel(
        config_paths=_config_paths(),
        task_registrar=_register_demo_tasks,
    )
    manager = BootstrapManager(kernel)
    report = manager.bootstrap()
    report_path = _write_bootstrap_report(report, _reports_dir())

    if not report.success:
        failed = [r.task_name for r in report.task_results if r.status is TaskStatus.FAILED]
        print(f"[HMIP] bootstrap FAILED at step(s): {failed}", file=sys.stderr)
        print(f"[HMIP] full report written to {report_path}", file=sys.stderr)
        return 1

    mark_ready()
    print(
        f"[HMIP] bootstrap OK — execution_id={report.execution_id} "
        f"steps={len(report.task_results)}"
    )
    print(f"[HMIP] report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
