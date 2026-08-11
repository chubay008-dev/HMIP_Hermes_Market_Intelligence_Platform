"""Unit tests for platform_/health.py.

This package was renamed from `platform/` to `platform_/` after the
standard-library name collision broke test collection — see
ADR_010_platform_package_rename.md and SPRINT_6_STATUS.md.
"""

from __future__ import annotations

import pytest

from platform_.health import check_health, main


def test_check_health_returns_true_on_this_machine() -> None:
    # This test's own successful collection already proves Python
    # 3.12+ is running (pyproject.toml's requires-python), so the
    # underlying diagnostic should pass here by construction.
    assert check_health() is True


def test_main_returns_zero_when_healthy() -> None:
    assert main() == 0


def test_main_returns_one_when_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform_.health.check_health", lambda: False)

    assert main() == 1
