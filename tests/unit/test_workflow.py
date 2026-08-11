"""Unit tests for WorkflowDefinition, TaskDefinition, RetryPolicy, and
WorkflowLoader. Validation failures raise WorkflowParseException per
05_Interface_Contract.md section 6.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import WorkflowParseException
from core.workflow import RetryPolicy, TaskDefinition, WorkflowDefinition, WorkflowLoader


def _task(task_id: str, deps: tuple[str, ...] = ()) -> TaskDefinition:
    return TaskDefinition(id=task_id, type="adapter", dependencies=deps)


def test_retry_policy_defaults() -> None:
    policy = RetryPolicy()

    assert policy.strategy == "none"
    assert policy.max_attempts == 1
    assert policy.base_delay_ms == 0.0


def test_retry_policy_rejects_zero_attempts() -> None:
    with pytest.raises(WorkflowParseException):
        RetryPolicy(max_attempts=0)


def test_retry_policy_rejects_negative_delay() -> None:
    with pytest.raises(WorkflowParseException):
        RetryPolicy(base_delay_ms=-1)


def test_task_definition_rejects_empty_id() -> None:
    with pytest.raises(WorkflowParseException):
        TaskDefinition(id="", type="adapter")


def test_task_definition_rejects_invalid_type() -> None:
    with pytest.raises(WorkflowParseException):
        TaskDefinition(id="collect", type="not_a_real_type")


def test_workflow_definition_requires_at_least_one_task() -> None:
    with pytest.raises(WorkflowParseException):
        WorkflowDefinition(id="WF-1", version="1.0.0", owner="team", tasks=())


def test_workflow_definition_rejects_duplicate_task_ids() -> None:
    with pytest.raises(WorkflowParseException):
        WorkflowDefinition(
            id="WF-1",
            version="1.0.0",
            owner="team",
            tasks=(_task("collect"), _task("collect")),
        )


def test_workflow_definition_rejects_unknown_dependency() -> None:
    with pytest.raises(WorkflowParseException):
        WorkflowDefinition(
            id="WF-1",
            version="1.0.0",
            owner="team",
            tasks=(_task("extract", deps=("collect",)),),
        )


def test_workflow_definition_get_task_returns_matching_task() -> None:
    workflow = WorkflowDefinition(
        id="WF-1",
        version="1.0.0",
        owner="team",
        tasks=(_task("collect"), _task("extract", deps=("collect",))),
    )

    assert workflow.get_task("extract").id == "extract"


def test_workflow_definition_get_task_raises_for_missing_task() -> None:
    workflow = WorkflowDefinition(
        id="WF-1", version="1.0.0", owner="team", tasks=(_task("collect"),)
    )

    with pytest.raises(WorkflowParseException):
        workflow.get_task("does_not_exist")


def test_loader_loads_valid_workflow_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text(
        """
id: WF-TEST
version: "1.0.0"
owner: Platform Team
tasks:
  - id: collect
    type: adapter
  - id: extract
    type: prompt
    dependencies: [collect]
""",
        encoding="utf-8",
    )

    workflow = WorkflowLoader().load(path)

    assert workflow.id == "WF-TEST"
    assert [t.id for t in workflow.tasks] == ["collect", "extract"]
    assert workflow.get_task("extract").dependencies == ("collect",)


def test_loader_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorkflowParseException):
        WorkflowLoader().load(tmp_path / "missing.yaml")


def test_loader_parses_retry_policy_dict(tmp_path: Path) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text(
        """
id: WF-TEST
version: "1.0.0"
owner: Platform Team
tasks:
  - id: collect
    type: adapter
    retry_policy:
      strategy: exponential_backoff
      max_attempts: 3
      base_delay_ms: 100
""",
        encoding="utf-8",
    )

    workflow = WorkflowLoader().load(path)
    task = workflow.get_task("collect")

    assert task.retry_policy.strategy == "exponential_backoff"
    assert task.retry_policy.max_attempts == 3
    assert task.retry_policy.base_delay_ms == 100.0


def test_task_definition_accepts_output_template() -> None:
    task = TaskDefinition(id="collect", type="adapter", output="${collect.output}")

    assert task.output == "${collect.output}"


def test_task_definition_output_defaults_to_none() -> None:
    task = TaskDefinition(id="collect", type="adapter")

    assert task.output is None


def test_workflow_definition_retry_policy_defaults() -> None:
    workflow = WorkflowDefinition(
        id="WF-1", version="1.0.0", owner="team", tasks=(_task("collect"),)
    )

    assert workflow.retry_policy == RetryPolicy()


def test_workflow_definition_accepts_custom_retry_policy() -> None:
    workflow = WorkflowDefinition(
        id="WF-1",
        version="1.0.0",
        owner="team",
        tasks=(_task("collect"),),
        retry_policy=RetryPolicy(strategy="exponential_backoff", max_attempts=5),
    )

    assert workflow.retry_policy.strategy == "exponential_backoff"
    assert workflow.retry_policy.max_attempts == 5


def test_loader_parses_workflow_level_retry_policy(tmp_path: Path) -> None:
    path = tmp_path / "wf.yaml"
    path.write_text(
        """
id: WF-TEST
version: "1.0.0"
owner: Platform Team
retry_policy:
  strategy: exponential_backoff
  max_attempts: 4
tasks:
  - id: collect
    type: adapter
""",
        encoding="utf-8",
    )

    workflow = WorkflowLoader().load(path)

    assert workflow.retry_policy.strategy == "exponential_backoff"
    assert workflow.retry_policy.max_attempts == 4
