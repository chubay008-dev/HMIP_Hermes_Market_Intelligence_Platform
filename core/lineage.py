"""Lineage tracing.

`LineageRecord` shape locked by 12_Data_Contract.md section 8.1.
`InMemoryLineageTracer` and `PersistentLineageTracer` both conform to
05_Interface_Contract.md section 4.8's `LineageTracer` protocol
(`record_trace()` only) plus a `list_records()` accessor that is NOT
part of the protocol — added because a write-only tracer nobody can
inspect would be untestable (05_Interface_Contract.md section 8:
"Test double phải dễ tạo mà không cần boot toàn hệ thống").

`InMemoryLineageTracer` was pulled forward from its originally-planned
Sprint 4 slot (10_Project_Backlog.md) in Sprint 3, because
15_Acceptance_Criteria.md section 3's Sprint 3 criteria explicitly
required "Lineage được ghi nhận" for the PRC-001 vertical slice.
`PersistentLineageTracer` is the actual Sprint 4 deliverable —
"Lineage records được tạo và lưu" / "Provenance trace có thể kiểm tra
được".
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Protocol


@dataclasses.dataclass(frozen=True)
class LineageRecord:
    """Locked shape: step, input_value, output_value, model_info,
    timestamp, integrity_hash (12_Data_Contract.md section 8.1)."""

    step: str
    input_value: Any
    output_value: Any
    model_info: str
    timestamp: float
    integrity_hash: str


class LineageTracer(Protocol):
    """Structural protocol used for type-hinting "any conforming
    tracer" in callers like `core.workflow_engine.WorkflowEngine`.

    Only `record_trace()` is part of the actual locked contract
    (05_Interface_Contract.md section 4.8); `list_records()` is
    included here purely for typing convenience so callers can read
    back results through this same type hint without a cast — both
    `InMemoryLineageTracer` and `PersistentLineageTracer` implement
    both methods via duck typing, neither inherits from this class.
    """

    def record_trace(
        self, step_id: str, input_val: Any, output_val: Any, model_info: str
    ) -> None: ...

    def list_records(self) -> tuple[LineageRecord, ...]: ...


def _compute_integrity_hash(output_val: Any) -> str:
    """Hash computed over the canonical (sorted-key) JSON form of the
    output when possible; falls back to `repr()` for non-JSON-
    serializable values so this never raises. Prefixed "sha256:" per
    the data contract's own example."""
    try:
        canonical = json.dumps(output_val, sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        canonical = repr(output_val)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class InMemoryLineageTracer:
    """Append-only, in-memory LineageTracer conforming to
    05_Interface_Contract.md section 4.8's protocol. Lost on process
    exit — use `PersistentLineageTracer` when durability across
    process restarts matters."""

    def __init__(self) -> None:
        self._records: list[LineageRecord] = []

    def record_trace(
        self,
        step_id: str,
        input_val: Any,
        output_val: Any,
        model_info: str,
    ) -> None:
        self._records.append(
            LineageRecord(
                step=step_id,
                input_value=input_val,
                output_value=output_val,
                model_info=model_info,
                timestamp=time.time(),
                integrity_hash=_compute_integrity_hash(output_val),
            )
        )

    def list_records(self) -> tuple[LineageRecord, ...]:
        """Not part of the locked protocol — see module docstring."""
        return tuple(self._records)


class PersistentLineageTracer:
    """Append-only, file-persisted LineageTracer conforming to
    05_Interface_Contract.md section 4.8's protocol.

    Each `record_trace()` call appends one JSON line to `path`
    immediately (no in-memory buffering) — a record is durable as soon
    as the call returns. `path` defaults to
    `knowledge/dynamic/lineage/lineage.jsonl` (project decision,
    resolving SPRINT_4_STATUS.md's open question — lineage records
    are runtime-derived, time-varying data, matching
    `knowledge/dynamic/`'s stated purpose per that folder's own
    `.gitkeep`) if not given explicitly; that default is relative to
    the process's current working directory, same as
    `platform_/bootstrap.py`'s own `HMIP_REPORT_DIR`/`HMIP_CONFIG_PATH`
    defaults.

    Note: `input_value`/`output_value` are round-tripped through JSON.
    A value that isn't natively JSON-serializable is written via its
    `str()` fallback (same as the integrity hash's own fallback) and
    read back as that string, not reconstructed as the original
    Python object — an inherent limitation of file-based persistence
    for arbitrary payloads.
    """

    DEFAULT_PATH = Path("knowledge/dynamic/lineage/lineage.jsonl")

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else self.DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record_trace(
        self,
        step_id: str,
        input_val: Any,
        output_val: Any,
        model_info: str,
    ) -> None:
        record = LineageRecord(
            step=step_id,
            input_value=input_val,
            output_value=output_val,
            model_info=model_info,
            timestamp=time.time(),
            integrity_hash=_compute_integrity_hash(output_val),
        )
        line = json.dumps(dataclasses.asdict(record), sort_keys=True, default=str)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def list_records(self) -> tuple[LineageRecord, ...]:
        """Not part of the locked protocol. Reads back every record
        currently persisted at `path` — empty tuple if the file
        doesn't exist yet (nothing recorded so far, not an error)."""
        return self.query()

    def query(self, *, step: str | None = None) -> tuple[LineageRecord, ...]:
        """Not part of the locked protocol. Reads every persisted
        record, optionally filtered to a single `step` id — the
        "Provenance trace có thể kiểm tra được" acceptance criterion."""
        if not self._path.exists():
            return ()
        records: list[LineageRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            record = LineageRecord(**raw)
            if step is None or record.step == step:
                records.append(record)
        return tuple(records)
