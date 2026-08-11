"""ExecutionContext: the object that threads through a single HMIP
execution, linking runtime behavior, workflow, trace, and lineage.

Shape is locked by 05_Interface_Contract.md section 5.1 /
12_Data_Contract.md section 4.1 — exactly six fields, no more. Do not
add fields here without updating those documents first (per
05_Interface_Contract.md section 9).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable execution context.

    `execution_id` and `trace_id` are unique per execution/trace.
    `correlation_id` groups steps belonging to the same business
    transaction. `metadata` should be treated as structured and
    effectively immutable by callers even though the dict container
    itself is mutable at the Python level — it is also where
    supplementary, non-contractual linkage data (e.g. a derived
    child's `parent_trace_id`) is carried, since the dataclass itself
    may not gain extra top-level fields.
    """

    execution_id: str
    trace_id: str
    correlation_id: str
    epoch: int
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionContextFactory:
    """Factory responsible for producing unique, well-formed
    ExecutionContext instances. This is the only sanctioned way to
    create an ExecutionContext."""

    @staticmethod
    def create(
        *,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        epoch: int = 0,
    ) -> ExecutionContext:
        """Create a new ExecutionContext with fresh execution_id/trace_id.

        `correlation_id` is generated if not supplied, so unrelated
        top-level executions still get a stable correlation identity.
        """
        return ExecutionContext(
            execution_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            correlation_id=correlation_id or str(uuid.uuid4()),
            epoch=epoch,
            timestamp=time.time(),
            metadata=dict(metadata) if metadata else {},
        )

    @staticmethod
    def derive(parent: ExecutionContext, *, epoch: int | None = None) -> ExecutionContext:
        """Create a child ExecutionContext for a sub-execution, keeping
        the same correlation_id. The parent's `trace_id` is preserved
        under `metadata["parent_trace_id"]` since `parent_trace_id` is
        not part of the locked ExecutionContext shape."""
        child_metadata = dict(parent.metadata)
        child_metadata["parent_trace_id"] = parent.trace_id
        return ExecutionContext(
            execution_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            correlation_id=parent.correlation_id,
            epoch=epoch if epoch is not None else parent.epoch + 1,
            timestamp=time.time(),
            metadata=child_metadata,
        )
