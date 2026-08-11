"""Core runtime exception hierarchy.

Exception class names for Registry/Config/Workflow-parse/
Workflow-execution/Decision errors are locked by
05_Interface_Contract.md section 6. Per explicit project decision,
code raises the **exact** locked class for every case in that
category — no finer-grained subclasses. Specific failure reasons are
distinguished via the `code` attribute (e.g. `"REGISTRY_DUPLICATE_TASK"`
vs `"REGISTRY_NOT_READY"`), not via exception subtype. Callers that
need to branch on the specific failure should inspect `.code`, not
use `isinstance()` against a subclass.
"""

from __future__ import annotations


class HMIPError(Exception):
    """Base class for all HMIP core runtime errors."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class BootstrapError(HMIPError):
    """Raised when the bootstrap sequence fails at any step. Not
    covered by 05_Interface_Contract.md section 6's named list, so it
    keeps its original name."""


class RegistryStateException(HMIPError):
    """Raised for every TaskRegistry error (05_Interface_Contract.md
    section 6: "Registry errors phải raise RegistryStateException").
    Distinguish specific failures via `.code`: `REGISTRY_NOT_READY`,
    `REGISTRY_INVALID_TASK_SCHEMA`, `REGISTRY_DUPLICATE_TASK`,
    `REGISTRY_UNKNOWN_STATE`, `REGISTRY_INVALID_TRANSITION`."""


class ConfigValidationException(HMIPError):
    """Raised for every config loading/merging/expansion/validation
    error (section 6: "Config errors phải raise
    ConfigValidationException")."""


class WorkflowParseException(HMIPError):
    """Raised for every workflow structural-validation failure,
    including DAG planning/cycle-detection failures — planning happens
    before any task executes, so it is treated as parse-time, not
    runtime (section 6: "Workflow parsing errors phải raise
    WorkflowParseException"). Distinguish via `.code`, e.g.
    `PLANNER_CYCLE_DETECTED` vs `WORKFLOW_UNKNOWN_DEPENDENCY`."""


class WorkflowExecutionException(HMIPError):
    """Reserved for workflow *runtime* failures once a WorkflowEngine
    exists to raise it (05_Interface_Contract.md section 4.3). Not
    currently raised anywhere: `TaskExecutor` intentionally returns a
    FAILED `TaskExecutionResult` instead of raising, mirroring
    `BootstrapKernel`'s fail-observably-without-raising design."""


class DecisionEngineException(HMIPError):
    """Raised for invalid DecisionResult construction and, once a
    concrete DecisionEngine exists (Sprint 3+), for its evaluation
    failures (section 6: "Decision errors phải raise
    DecisionEngineException")."""


class KnowledgeValidationException(HMIPError):
    """Raised for ontology/master/dynamic data validation failures in
    the Knowledge Layer (01_System_Specification.md section 2.3).
    Not named in 05_Interface_Contract.md section 6's list (that list
    only covers Registry/Config/Workflow-parse/Workflow-execution/
    Decision) — this is a new category introduced for Sprint 4,
    following the same "one exact class per layer-concern" pattern."""


class EventDeliveryError(HMIPError):
    """Raised when one or more subscribed handlers raise during
    EventBus.publish, or when a published event dict is malformed. Not
    covered by section 6's named list. Carries the original exceptions
    in `errors`."""

    def __init__(self, message: str, *, code: str, errors: list[BaseException]) -> None:
        super().__init__(message, code=code)
        self.errors = errors
