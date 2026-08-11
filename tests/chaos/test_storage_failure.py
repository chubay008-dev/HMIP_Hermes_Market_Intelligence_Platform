"""Chaos test: storage failure (08_Testing_Standard.md section 11).

Simulates the underlying storage becoming unreadable mid-read (disk
I/O error, permission revoked, network filesystem drop, etc.) —
distinct from "file doesn't exist", which is an ordinary config error
already covered elsewhere. Found and fixed a real gap while writing
this: `ConfigLoader._read_yaml` previously only caught
`yaml.YAMLError`; an `OSError` from `Path.read_text()` would have
propagated as a raw, uncaught exception instead of the locked
`ConfigValidationException`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import ConfigLoader
from core.exceptions import ConfigValidationException


def test_config_load_fails_fast_with_locked_exception_on_storage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("service:\n  name: hmip\n", encoding="utf-8")

    def broken_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("simulated storage failure: I/O error")

    monkeypatch.setattr(Path, "read_text", broken_read_text)

    loader = ConfigLoader([cfg])

    with pytest.raises(ConfigValidationException) as exc_info:
        loader.load()

    assert exc_info.value.code == "CONFIG_STORAGE_FAILURE"


def test_config_load_error_message_identifies_the_failing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("service:\n  name: hmip\n", encoding="utf-8")

    def broken_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("disk read error")

    monkeypatch.setattr(Path, "read_text", broken_read_text)

    loader = ConfigLoader([cfg])

    with pytest.raises(ConfigValidationException) as exc_info:
        loader.load()

    assert str(cfg) in exc_info.value.message


def test_config_loader_does_not_leak_raw_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The system must not crash with an unhandled OSError — it must
    surface the locked exception taxonomy, per
    15_Acceptance_Criteria.md section 4: "Error handling có taxonomy
    rõ"."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("a: 1\n", encoding="utf-8")

    def broken_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("device unavailable")

    monkeypatch.setattr(Path, "read_text", broken_read_text)

    loader = ConfigLoader([cfg])

    try:
        loader.load()
        pytest.fail("expected ConfigValidationException to be raised")
    except ConfigValidationException:
        pass  # expected — the taxonomy held
    except OSError:
        pytest.fail("raw OSError leaked past ConfigLoader's boundary")
