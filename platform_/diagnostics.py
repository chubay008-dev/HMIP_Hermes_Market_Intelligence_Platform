"""Environment diagnostics run before/around bootstrap. Does not perform
bootstrap itself — see `platform_/bootstrap.py` and `core/bootstrap.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    passed: bool
    detail: str


def check_python_version(minimum: tuple[int, int] = (3, 12)) -> DiagnosticResult:
    current = sys.version_info[:2]
    passed = current >= minimum
    return DiagnosticResult(
        name="python_version",
        passed=passed,
        detail=f"required>={minimum}, found={current}",
    )


def run_diagnostics() -> list[DiagnosticResult]:
    """Run all environment diagnostics. Sprint 1 covers Python version
    only; more checks (config paths present, required env vars) are
    expected to be added alongside later sprints."""
    return [check_python_version()]
