"""Readiness check.

09_Deployment_Guide.md section 8: "kiểm tra bootstrap đã hoàn tất,
registry đã freeze, config đã valid, runtime sẵn sàng nhận workflow."

This project runs bootstrap once at process startup with no
long-running request loop yet (see `platform_/health.py`'s module
docstring for the same architectural note), so readiness is modeled
as a marker file written by `platform_/bootstrap.py::main()`
immediately after a successful bootstrap — appropriate for a
batch/Job-style container (checked between runs, or by an init
container / sidecar), not a traditional HTTP readinessProbe. If a
long-running service model is added later, this should become a real
HTTP endpoint instead.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

READY_FILE_ENV_VAR = "HMIP_READY_FILE"


def ready_file_path() -> Path:
    """`HMIP_READY_FILE` env var if set, else a path under the OS
    temp directory (portable across Linux containers and local
    Windows/macOS dev machines — no hardcoded `/tmp`)."""
    override = os.environ.get(READY_FILE_ENV_VAR)
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "hmip_ready"


def mark_ready() -> None:
    """Called by `platform_/bootstrap.py::main()` after a successful
    bootstrap. Idempotent — safe to call on every successful run."""
    path = ready_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ready\n", encoding="utf-8")


def clear_ready() -> None:
    """Removes the readiness marker, if present. Not currently called
    anywhere in this codebase (there is no shutdown hook that runs
    before the next bootstrap attempt) — provided for a future
    long-running service model, or for tests that need a clean
    slate."""
    path = ready_file_path()
    if path.exists():
        path.unlink()


def check_readiness() -> bool:
    return ready_file_path().exists()


def main() -> int:
    ready = check_readiness()
    print("READY" if ready else "NOT_READY")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
