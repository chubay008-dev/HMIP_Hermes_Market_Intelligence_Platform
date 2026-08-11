"""Unit tests for platform_/bootstrap.py's CLI entrypoint.

Uses `HMIP_REPORT_DIR`/`HMIP_READY_FILE` env var overrides so nothing
touches this repository's real `reports/` directory or the real OS
temp directory during test runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from platform_.bootstrap import _config_paths, _reports_dir, _write_bootstrap_report, main
from platform_.readiness import READY_FILE_ENV_VAR, check_readiness


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HMIP_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv(READY_FILE_ENV_VAR, str(tmp_path / "ready_marker"))


def test_config_paths_uses_env_var_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "custom_config"
    monkeypatch.setenv("HMIP_CONFIG_PATH", str(override))

    paths = _config_paths()

    assert paths == [
        override / "runtime.yaml",
        override / "logging.yaml",
        override / "deployment.yaml",
    ]


def test_config_paths_falls_back_to_relative_config_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HMIP_CONFIG_PATH", raising=False)

    paths = _config_paths()

    assert paths == [
        Path("config/runtime.yaml"),
        Path("config/logging.yaml"),
        Path("config/deployment.yaml"),
    ]


def test_reports_dir_uses_env_var_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "custom_reports"
    monkeypatch.setenv("HMIP_REPORT_DIR", str(override))

    assert _reports_dir() == override


def test_reports_dir_falls_back_to_relative_reports_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HMIP_REPORT_DIR", raising=False)

    assert _reports_dir() == Path("reports")


def test_write_bootstrap_report_writes_valid_json(tmp_path: Path) -> None:
    from core.models import BootstrapReport, BootstrapStatus

    report = BootstrapReport(execution_id="exec-test", status=BootstrapStatus.SUCCESS)

    path = _write_bootstrap_report(report, tmp_path)

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["execution_id"] == "exec-test"
    assert data["status"] == "SUCCESS"


def test_main_succeeds_writes_report_and_marks_ready() -> None:
    exit_code = main()

    assert exit_code == 0
    assert check_readiness() is True


def test_main_success_report_is_written_to_configured_dir(tmp_path: Path) -> None:
    main()

    reports_dir = tmp_path / "reports"
    report_files = list(reports_dir.glob("bootstrap_*.json"))
    assert len(report_files) == 1


def test_main_fails_and_does_not_mark_ready_when_config_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point bootstrap at a directory with no config files.
    monkeypatch.chdir(tmp_path)

    exit_code = main()

    assert exit_code == 1
    assert check_readiness() is False


def test_main_still_writes_a_report_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HMIP_REPORT_DIR", str(tmp_path / "reports"))

    main()

    reports_dir = tmp_path / "reports"
    report_files = list(reports_dir.glob("bootstrap_*.json"))
    assert len(report_files) == 1
    data = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert data["status"] == "FAILED"
