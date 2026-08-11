"""Unit tests for ExecutionContext and ExecutionContextFactory.

Shape locked by 05_Interface_Contract.md section 5.1 /
12_Data_Contract.md section 4.1: exactly execution_id, trace_id,
correlation_id, epoch, timestamp, metadata — no more.
"""

from __future__ import annotations

import dataclasses

import pytest

from core.context import ExecutionContextFactory


def test_create_generates_unique_ids() -> None:
    ctx_a = ExecutionContextFactory.create()
    ctx_b = ExecutionContextFactory.create()

    assert ctx_a.execution_id != ctx_b.execution_id
    assert ctx_a.trace_id != ctx_b.trace_id


def test_create_defaults_correlation_id_when_not_provided() -> None:
    ctx = ExecutionContextFactory.create()

    assert ctx.correlation_id
    assert isinstance(ctx.correlation_id, str)


def test_create_uses_provided_correlation_id() -> None:
    ctx = ExecutionContextFactory.create(correlation_id="corr-123")

    assert ctx.correlation_id == "corr-123"


def test_context_metadata_defaults_to_empty_dict() -> None:
    ctx = ExecutionContextFactory.create()

    assert ctx.metadata == {}


def test_context_metadata_accepts_caller_supplied_dict() -> None:
    ctx = ExecutionContextFactory.create(metadata={"tenant_id": "acme"})

    assert ctx.metadata == {"tenant_id": "acme"}


def test_context_has_exactly_the_locked_field_set() -> None:
    ctx = ExecutionContextFactory.create()
    field_names = {f.name for f in dataclasses.fields(ctx)}

    assert field_names == {
        "execution_id",
        "trace_id",
        "correlation_id",
        "epoch",
        "timestamp",
        "metadata",
    }


def test_context_is_frozen_dataclass() -> None:
    ctx = ExecutionContextFactory.create()

    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.execution_id = "mutated"  # type: ignore[misc]


def test_derive_keeps_correlation_id_and_links_parent_trace_via_metadata() -> None:
    parent = ExecutionContextFactory.create(correlation_id="corr-abc")
    child = ExecutionContextFactory.derive(parent)

    assert child.correlation_id == parent.correlation_id
    assert child.metadata["parent_trace_id"] == parent.trace_id
    assert child.trace_id != parent.trace_id
    assert child.epoch == parent.epoch + 1


def test_derive_preserves_parent_metadata() -> None:
    parent = ExecutionContextFactory.create(metadata={"tenant_id": "acme"})
    child = ExecutionContextFactory.derive(parent)

    assert child.metadata["tenant_id"] == "acme"
    assert child.metadata["parent_trace_id"] == parent.trace_id
