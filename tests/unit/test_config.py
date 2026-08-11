"""Unit tests for ConfigLoader, conforming to 05_Interface_Contract.md
section 4.7's separate load()/merge()/validate()/freeze() methods.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import ConfigLoader
from core.exceptions import ConfigValidationException

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def test_load_returns_plain_mutable_dict(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("service:\n  name: hmip\n", encoding="utf-8")

    loader = ConfigLoader([cfg])
    raw = loader.load()

    assert isinstance(raw, dict)
    raw["service"]["name"] = "mutated"  # must not raise — not frozen yet
    assert raw["service"]["name"] == "mutated"


def test_load_merges_multiple_files_in_order(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    base.write_text("service:\n  name: hmip\n  version: 1\n", encoding="utf-8")
    override = tmp_path / "override.yaml"
    override.write_text("service:\n  version: 2\n", encoding="utf-8")

    loader = ConfigLoader([base, override])
    raw = loader.load()

    assert raw["service"]["name"] == "hmip"
    assert raw["service"]["version"] == 2


def test_merge_deep_merges_dicts_without_reading_files() -> None:
    loader = ConfigLoader([])

    merged = loader.merge({"a": {"x": 1}}, {"a": {"y": 2}})

    assert merged == {"a": {"x": 1, "y": 2}}


def test_load_expands_environment_variables(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("env_name: ${HMIP_TEST_VAR}\n", encoding="utf-8")

    loader = ConfigLoader([cfg], env={"HMIP_TEST_VAR": "resolved"})
    raw = loader.load()

    assert raw["env_name"] == "resolved"


def test_load_uses_default_when_variable_unset(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("env_name: ${HMIP_UNSET_VAR:-fallback}\n", encoding="utf-8")

    loader = ConfigLoader([cfg], env={})
    raw = loader.load()

    assert raw["env_name"] == "fallback"


def test_load_missing_required_variable_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("env_name: ${HMIP_MISSING_VAR}\n", encoding="utf-8")

    loader = ConfigLoader([cfg], env={})

    with pytest.raises(ConfigValidationException):
        loader.load()


def test_load_missing_file_raises() -> None:
    loader = ConfigLoader([Path("/nonexistent/missing.yaml")])

    with pytest.raises(ConfigValidationException):
        loader.load()


def test_validate_accepts_a_dict() -> None:
    loader = ConfigLoader([])
    loader.validate({"a": 1})  # must not raise


def test_load_can_be_called_multiple_times() -> None:
    loader = ConfigLoader([CONFIG_DIR / "runtime.yaml"], env={"HMIP_ENV": "test"})

    first = loader.load()
    second = loader.load()

    assert first == second
    assert first is not second  # independent dicts, not shared state


def test_freeze_produces_immutable_snapshot_with_fingerprint() -> None:
    loader = ConfigLoader([CONFIG_DIR / "runtime.yaml"], env={"HMIP_ENV": "test"})
    raw = loader.load()
    loader.validate(raw)

    frozen = loader.freeze(raw)

    assert frozen.get("runtime")["environment"] == "test"
    assert frozen.get("runtime")["service_name"] == "hmip"
    assert len(frozen.fingerprint) == 64  # sha256 hex digest length


def test_freeze_snapshot_is_independent_of_source_dict_mutation() -> None:
    loader = ConfigLoader([CONFIG_DIR / "runtime.yaml"], env={"HMIP_ENV": "test"})
    raw = loader.load()
    frozen = loader.freeze(raw)

    raw["runtime"]["environment"] = "mutated-after-freeze"

    assert frozen.get("runtime")["environment"] == "test"
