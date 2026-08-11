"""Unit tests for shared data contracts in core/models.py.

Shapes locked by 05_Interface_Contract.md section 5 /
12_Data_Contract.md sections 4.2-4.3 and 5.3.
"""

from __future__ import annotations

import dataclasses

import pytest

from core.exceptions import DecisionEngineException
from core.models import (
    BootstrapReport,
    BootstrapStatus,
    DecisionResult,
    TaskExecutionResult,
    TaskStatus,
)


def test_task_execution_result_has_exactly_the_locked_field_set() -> None:
    result = TaskExecutionResult(task_name="collect", status=TaskStatus.SUCCESS, duration_ms=1.0)
    field_names = {f.name for f in dataclasses.fields(result)}

    assert field_names == {"task_name", "status", "duration_ms", "error"}


def test_task_execution_result_error_defaults_to_none() -> None:
    result = TaskExecutionResult(task_name="collect", status=TaskStatus.SUCCESS, duration_ms=1.0)

    assert result.error is None


def test_bootstrap_report_has_exactly_the_locked_field_set() -> None:
    report = BootstrapReport(execution_id="exec-1", status=BootstrapStatus.SUCCESS)
    field_names = {f.name for f in dataclasses.fields(report)}

    assert field_names == {
        "execution_id",
        "status",
        "task_results",
        "runtime_version",
        "kernel_version",
    }


def test_bootstrap_report_success_property_matches_status() -> None:
    success_report = BootstrapReport(execution_id="exec-1", status=BootstrapStatus.SUCCESS)
    failed_report = BootstrapReport(execution_id="exec-2", status=BootstrapStatus.FAILED)

    assert success_report.success is True
    assert failed_report.success is False


def test_bootstrap_report_version_defaults_are_populated() -> None:
    report = BootstrapReport(execution_id="exec-1", status=BootstrapStatus.SUCCESS)

    assert report.runtime_version
    assert report.kernel_version


def test_bootstrap_report_runtime_version_reads_env_var_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """09_Deployment_Guide.md section 5: HMIP_RUNTIME_VERSION is a
    documented, overridable env var."""
    monkeypatch.setenv("HMIP_RUNTIME_VERSION", "9.9.9-test")

    report = BootstrapReport(execution_id="exec-1", status=BootstrapStatus.SUCCESS)

    assert report.runtime_version == "9.9.9-test"


def test_bootstrap_report_kernel_version_reads_env_var_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HMIP_KERNEL_VERSION", "TEST-KERNEL")

    report = BootstrapReport(execution_id="exec-1", status=BootstrapStatus.SUCCESS)

    assert report.kernel_version == "TEST-KERNEL"


def test_bootstrap_report_version_falls_back_when_env_var_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HMIP_RUNTIME_VERSION", raising=False)
    monkeypatch.delenv("HMIP_KERNEL_VERSION", raising=False)

    report = BootstrapReport(execution_id="exec-1", status=BootstrapStatus.SUCCESS)

    # runtime_version is tied to the real installed package version
    # (shared/constants.py) rather than a fixed literal, so this only
    # checks it resolved to *something*, not an exact string.
    assert report.runtime_version
    assert report.kernel_version == "1.0.0"


def test_decision_result_has_exactly_the_locked_field_set() -> None:
    decision = DecisionResult(decision="IGNORE", confidence=0.9, reason="within tolerance")
    field_names = {f.name for f in dataclasses.fields(decision)}

    assert field_names == {"decision", "confidence", "reason", "recommended_action"}


def test_decision_result_accepts_all_allowed_decisions() -> None:
    for decision_value in ("IGNORE", "ALERT", "ESCALATE", "HUMAN_REVIEW"):
        result = DecisionResult(decision=decision_value, confidence=0.5, reason="test")
        assert result.decision == decision_value


def test_decision_result_rejects_unknown_decision_value() -> None:
    with pytest.raises(DecisionEngineException):
        DecisionResult(decision="NOT_A_REAL_DECISION", confidence=0.5, reason="test")


def test_decision_result_rejects_confidence_above_one() -> None:
    with pytest.raises(DecisionEngineException):
        DecisionResult(decision="ALERT", confidence=1.5, reason="test")


def test_decision_result_rejects_negative_confidence() -> None:
    with pytest.raises(DecisionEngineException):
        DecisionResult(decision="ALERT", confidence=-0.1, reason="test")


def test_decision_result_rejects_empty_reason() -> None:
    with pytest.raises(DecisionEngineException):
        DecisionResult(decision="ALERT", confidence=0.5, reason="")


def test_decision_result_recommended_action_defaults_to_none() -> None:
    result = DecisionResult(decision="ALERT", confidence=0.8, reason="price drop detected")

    assert result.recommended_action is None


def test_decision_result_accepts_recommended_action() -> None:
    result = DecisionResult(
        decision="ESCALATE",
        confidence=0.95,
        reason="anomaly detected",
        recommended_action="notify_pricing_team",
    )

    assert result.recommended_action == "notify_pricing_team"
