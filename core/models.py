"""Shared runtime data contracts: TaskExecutionResult, BootstrapReport,
DecisionResult.

Shapes are locked by 05_Interface_Contract.md section 5 /
12_Data_Contract.md sections 4.2-4.3 and 5.3. Do not add fields beyond
what those documents specify without updating them first (per
05_Interface_Contract.md section 9 / 12_Data_Contract.md section 12).
Read-only convenience `@property` members that derive from existing
fields (e.g. `BootstrapReport.success`) are not considered new fields
— they add no stored state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum

from core.exceptions import DecisionEngineException
from shared.constants import KERNEL_VERSION, RUNTIME_VERSION


def _env_or_default_runtime_version() -> str:
    """09_Deployment_Guide.md section 5 lists `HMIP_RUNTIME_VERSION`
    as a required env var — read at each `BootstrapReport`
    construction (a plain dataclass default is evaluated once at
    import time, which would miss an env var set for this specific
    run), falling back to the placeholder default if unset."""
    return os.environ.get("HMIP_RUNTIME_VERSION", RUNTIME_VERSION)


def _env_or_default_kernel_version() -> str:
    """Same as above, for `HMIP_KERNEL_VERSION`."""
    return os.environ.get("HMIP_KERNEL_VERSION", KERNEL_VERSION)


# Allowed TaskExecutionResult.status values (12_Data_Contract.md
# section 4.2). Sprint 2's executor only ever produces SUCCESS or
# FAILED; RETRYING/CANCELLED are reserved for a future sprint that
# reports intermediate/cancelled states, not unused dead values.
class TaskStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TaskExecutionResult:
    """Result of executing a single task (a workflow task or a
    bootstrap step — both are "tasks" per this shared contract).

    Locked shape: `task_name`, `status`, `duration_ms`, `error`. Any
    output/return payload a task produces flows through a side
    channel appropriate to the caller (e.g. `TaskExecutor`'s optional
    `outputs` mapping), not through this result object.
    """

    task_name: str
    status: TaskStatus
    duration_ms: float
    error: str | None = None


# Allowed BootstrapReport.status values (12_Data_Contract.md section
# 4.3). BootstrapKernel is fail-fast (see core/bootstrap.py), so it
# never actually produces PARTIAL — that value is reserved for a
# design that tolerates non-critical step failures, which this kernel
# does not (yet) implement.
class BootstrapStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class BootstrapReport:
    """Full bootstrap outcome, emitted as the final bootstrap step."""

    execution_id: str
    status: BootstrapStatus
    task_results: tuple[TaskExecutionResult, ...] = field(default_factory=tuple)
    runtime_version: str = field(default_factory=_env_or_default_runtime_version)
    kernel_version: str = field(default_factory=_env_or_default_kernel_version)

    @property
    def success(self) -> bool:
        """Convenience read-only view — not a stored field."""
        return self.status is BootstrapStatus.SUCCESS


# Allowed high-level decision outcomes (03_Domain_Specification.md
# section 7 / 12_Data_Contract.md section 5.3).
DECISION_IGNORE = "IGNORE"
DECISION_ALERT = "ALERT"
DECISION_ESCALATE = "ESCALATE"
DECISION_HUMAN_REVIEW = "HUMAN_REVIEW"
ALLOWED_DECISIONS = frozenset(
    {DECISION_IGNORE, DECISION_ALERT, DECISION_ESCALATE, DECISION_HUMAN_REVIEW}
)


@dataclass(frozen=True)
class DecisionResult:
    """High-level decision output shared across domain decision
    engines. Locked shape: `decision`, `confidence`, `reason`,
    `recommended_action`."""

    decision: str
    confidence: float
    reason: str
    recommended_action: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in ALLOWED_DECISIONS:
            raise DecisionEngineException(
                f"decision '{self.decision}' is not an allowed value "
                f"({sorted(ALLOWED_DECISIONS)})",
                code="DECISION_INVALID_VALUE",
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise DecisionEngineException(
                f"confidence must be within 0.0..1.0, got {self.confidence}",
                code="DECISION_INVALID_CONFIDENCE",
            )
        if not self.reason:
            raise DecisionEngineException(
                "reason must not be empty", code="DECISION_MISSING_REASON"
            )
