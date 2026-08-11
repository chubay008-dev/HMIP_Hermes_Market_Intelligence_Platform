"""Unit tests for platform_/readiness.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from platform_.readiness import (
    READY_FILE_ENV_VAR,
    check_readiness,
    clear_ready,
    main,
    mark_ready,
    ready_file_path,
)


def test_ready_file_path_uses_env_var_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "custom_ready_marker"
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(override))

    assert ready_file_path() == override


def test_ready_file_path_falls_back_to_temp_dir_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(READY_FILE_ENV_VAR, raising=False)

    path = ready_file_path()

    assert path.name == "hmip_ready"


def test_check_readiness_false_before_mark_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(tmp_path / "ready_marker"))

    assert check_readiness() is False


def test_mark_ready_then_check_readiness_is_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(tmp_path / "ready_marker"))

    mark_ready()

    assert check_readiness() is True


def test_mark_ready_creates_parent_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = tmp_path / "a" / "b" / "ready_marker"
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(nested))

    mark_ready()

    assert nested.exists()


def test_clear_ready_removes_the_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(tmp_path / "ready_marker"))
    mark_ready()

    clear_ready()

    assert check_readiness() is False


def test_clear_ready_is_a_noop_when_nothing_to_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(tmp_path / "never_written"))

    clear_ready()  # must not raise


def test_main_returns_zero_when_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(tmp_path / "ready_marker"))
    mark_ready()

    assert main() == 0


def test_main_returns_one_when_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(tmp_path / "never_written"))

    assert main() == 1
