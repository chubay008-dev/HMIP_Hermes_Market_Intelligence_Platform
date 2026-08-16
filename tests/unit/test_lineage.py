"""Unit tests for InMemoryLineageTracer and PersistentLineageTracer
(12_Data_Contract.md section 8.1 / 05_Interface_Contract.md section
4.8). PersistentLineageTracer is Sprint 4's actual deliverable
("Lineage records được tạo và lưu" / "Provenance trace có thể kiểm
tra được")."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.lineage import InMemoryLineageTracer, PersistentLineageTracer


def test_record_trace_appends_a_record() -> None:
    tracer = InMemoryLineageTracer()

    tracer.record_trace("extract", {"raw": "payload"}, {"price": 18500.0}, "task:extract:prompt")

    records = tracer.list_records()
    assert len(records) == 1
    assert records[0].step == "extract"
    assert records[0].output_value == {"price": 18500.0}
    assert records[0].model_info == "task:extract:prompt"


def test_record_trace_is_append_only_across_multiple_calls() -> None:
    tracer = InMemoryLineageTracer()

    tracer.record_trace("collect", {}, {"raw": True}, "task:collect:adapter")
    tracer.record_trace("extract", {}, {"price": 1.0}, "task:extract:prompt")

    records = tracer.list_records()
    assert [r.step for r in records] == ["collect", "extract"]


def test_record_trace_computes_integrity_hash_for_json_serializable_output() -> None:
    tracer = InMemoryLineageTracer()

    tracer.record_trace("extract", {}, {"price": 18500.0}, "task:extract:prompt")

    record = tracer.list_records()[0]
    assert record.integrity_hash.startswith("sha256:")
    assert len(record.integrity_hash) == len("sha256:") + 64


def test_record_trace_same_output_produces_same_hash() -> None:
    tracer = InMemoryLineageTracer()

    tracer.record_trace("a", {}, {"x": 1}, "m")
    tracer.record_trace("b", {}, {"x": 1}, "m")

    records = tracer.list_records()
    assert records[0].integrity_hash == records[1].integrity_hash


def test_record_trace_handles_non_json_serializable_output_without_raising() -> None:
    tracer = InMemoryLineageTracer()

    class Unserializable:
        pass

    tracer.record_trace("weird", {}, Unserializable(), "m")  # must not raise

    assert len(tracer.list_records()) == 1


# --- PersistentLineageTracer -----------------------------------------------


def test_persistent_tracer_appends_a_record(tmp_path: Path) -> None:
    tracer = PersistentLineageTracer(tmp_path / "lineage.jsonl")

    tracer.record_trace("extract", {"raw": "payload"}, {"price": 18500.0}, "task:extract:prompt")

    records = tracer.list_records()
    assert len(records) == 1
    assert records[0].step == "extract"
    assert records[0].output_value == {"price": 18500.0}


def test_persistent_tracer_creates_parent_directories(tmp_path: Path) -> None:
    nested_path = tmp_path / "a" / "b" / "c" / "lineage.jsonl"

    PersistentLineageTracer(nested_path)  # must not raise

    assert nested_path.parent.exists()


def test_persistent_tracer_list_records_empty_before_any_write(tmp_path: Path) -> None:
    tracer = PersistentLineageTracer(tmp_path / "lineage.jsonl")

    assert tracer.list_records() == ()


def test_persistent_tracer_survives_a_new_instance_pointed_at_the_same_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lineage.jsonl"
    writer = PersistentLineageTracer(path)
    writer.record_trace("collect", {}, {"raw": True}, "task:collect:adapter")
    writer.record_trace("extract", {}, {"price": 1.0}, "task:extract:prompt")

    # A brand-new tracer instance, not the one that wrote the records,
    # proves this is real file persistence and not in-process memory.
    reader = PersistentLineageTracer(path)
    records = reader.list_records()

    assert [r.step for r in records] == ["collect", "extract"]


def test_persistent_tracer_query_filters_by_step(tmp_path: Path) -> None:
    tracer = PersistentLineageTracer(tmp_path / "lineage.jsonl")
    tracer.record_trace("collect", {}, {"raw": True}, "m")
    tracer.record_trace("extract", {}, {"price": 1.0}, "m")
    tracer.record_trace("extract", {}, {"price": 2.0}, "m")

    results = tracer.query(step="extract")

    assert len(results) == 2
    assert all(r.step == "extract" for r in results)


def test_persistent_tracer_query_without_step_returns_everything(tmp_path: Path) -> None:
    tracer = PersistentLineageTracer(tmp_path / "lineage.jsonl")
    tracer.record_trace("collect", {}, {}, "m")
    tracer.record_trace("extract", {}, {}, "m")

    assert len(tracer.query()) == 2


def test_persistent_tracer_preserves_integrity_hash_across_reload(tmp_path: Path) -> None:
    path = tmp_path / "lineage.jsonl"
    PersistentLineageTracer(path).record_trace("a", {}, {"x": 1}, "m")

    record = PersistentLineageTracer(path).list_records()[0]

    assert record.integrity_hash.startswith("sha256:")


def test_persistent_tracer_defaults_to_knowledge_dynamic_lineage_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project decision (see SPRINT_4_STATUS.md): defaults to
    knowledge/dynamic/lineage/lineage.jsonl, relative to CWD.
    `monkeypatch.chdir` redirects that relative default under
    `tmp_path` so this test never touches the real repository."""
    monkeypatch.chdir(tmp_path)

    tracer = PersistentLineageTracer()
    tracer.record_trace("collect", {}, {"ok": True}, "m")

    expected_path = tmp_path / "knowledge" / "dynamic" / "lineage" / "lineage.jsonl"
    assert expected_path.exists()
    assert len(tracer.list_records()) == 1


def test_persistent_tracer_default_path_constant_matches_documented_location() -> None:
    assert PersistentLineageTracer.DEFAULT_PATH == Path(
        "knowledge/dynamic/lineage/lineage.jsonl"
    )


# --- Redaction (05_Interface_Contract.md §4.8 "Không ghi secret plaintext") ---


def test_inmemory_tracer_redacts_sensitive_keys_by_default() -> None:
    tracer = InMemoryLineageTracer()
    tracer.record_trace(
        "collect",
        {"token": "abc", "ok": 1},
        {"api_key": "fc-123", "price": 18500.0},
        "m",
    )

    record = tracer.list_records()[0]
    assert record.input_value == {"token": "***REDACTED***", "ok": 1}
    assert record.output_value == {"api_key": "***REDACTED***", "price": 18500.0}


def test_inmemory_tracer_redact_disabled_when_fields_none() -> None:
    tracer = InMemoryLineageTracer(redact_fields=None)
    tracer.record_trace("collect", {"token": "abc"}, {"secret": "s"}, "m")

    record = tracer.list_records()[0]
    assert record.input_value == {"token": "abc"}
    assert record.output_value == {"secret": "s"}


def test_inmemory_tracer_redacts_nested_payloads() -> None:
    tracer = InMemoryLineageTracer()
    tracer.record_trace(
        "collect",
        {"request": {"headers": {"password": "pw"}}},
        {},
        "m",
    )

    record = tracer.list_records()[0]
    assert record.input_value["request"]["headers"]["password"] == "***REDACTED***"


def test_persistent_tracer_redacts_sensitive_keys_in_persisted_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lineage.jsonl"
    PersistentLineageTracer(path).record_trace(
        "collect", {"token": "leak-me"}, {"price": 1.0}, "m"
    )

    raw = path.read_text(encoding="utf-8")
    assert "leak-me" not in raw
    assert "***REDACTED***" in raw

