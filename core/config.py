"""Configuration subsystem.

Contract locked by 05_Interface_Contract.md section 4.7: `load()`,
`merge()`, `validate()`, `freeze()` are separate public methods, not
one opaque pipeline. `load()` returns a plain (still mutable)
`dict[str, Any]` — it does NOT validate or freeze; callers must call
`validate()` then `freeze()` explicitly (see `core/bootstrap.py`'s
`_resolve_config` for the canonical call sequence). This also means
`ConfigLoader` is reusable across multiple `load()` calls, unlike
Sprint 1's single-use design.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from core.exceptions import ConfigValidationException

_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}")


class FrozenConfig:
    """Immutable, frozen configuration snapshot produced by
    `ConfigLoader.freeze()`. Satisfies the `Protocol`'s `freeze() ->
    object` return type via covariant return typing (a more specific
    type is a valid `object`)."""

    def __init__(self, data: Mapping[str, Any], fingerprint: str) -> None:
        self._data: Mapping[str, Any] = MappingProxyType(copy.deepcopy(dict(data)))
        self._fingerprint = fingerprint

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self._data))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"FrozenConfig(fingerprint={self._fingerprint!r})"


class ConfigLoader:
    """Loads, merges, validates, and freezes HMIP runtime
    configuration, conforming to 05_Interface_Contract.md section
    4.7's `ConfigLoader` protocol."""

    def __init__(
        self,
        config_paths: list[Path],
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._config_paths = config_paths
        self._env: dict[str, str] = dict(env) if env is not None else dict(os.environ)

    def load(self) -> dict[str, Any]:
        """Read every configured file, deep-merge them in order, expand
        `${VAR}` / `${VAR:-default}` placeholders, and resolve secrets
        (currently a pass-through stub — see SPRINT_1_STATUS.md).
        Returns a plain mutable dict; does NOT validate or freeze."""
        parsed = [self._read_yaml(path) for path in self._config_paths]
        merged = self.merge(*parsed)
        expanded = self._expand_variables(merged)
        return self._resolve_secrets(expanded)

    def merge(self, *configs: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for config in configs:
            result = self._deep_merge(result, config)
        return result

    def validate(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ConfigValidationException(
                "resolved config must be a mapping", code="CONFIG_INVALID_SHAPE"
            )

    def freeze(self, config: dict[str, Any]) -> FrozenConfig:
        fingerprint = self._fingerprint(config)
        return FrozenConfig(config, fingerprint)

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ConfigValidationException(
                f"config file not found: {path}", code="CONFIG_FILE_NOT_FOUND"
            )
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            # Storage failure (permission denied, I/O error, device
            # unavailable, etc.) — the file exists per the check above
            # but became unreadable between the check and the read, or
            # the underlying storage itself failed. Surfaced as the
            # same locked exception as any other config load failure,
            # not a raw OSError leaking past this boundary.
            raise ConfigValidationException(
                f"failed to read config file {path}: {exc}",
                code="CONFIG_STORAGE_FAILURE",
            ) from exc
        try:
            content = yaml.safe_load(raw_text) or {}
        except yaml.YAMLError as exc:
            raise ConfigValidationException(
                f"invalid yaml in {path}: {exc}", code="CONFIG_INVALID_YAML"
            ) from exc
        if not isinstance(content, dict):
            raise ConfigValidationException(
                f"config root must be a mapping: {path}", code="CONFIG_INVALID_ROOT"
            )
        return content

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _expand_variables(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: self._expand_variables(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._expand_variables(v) for v in data]
        if isinstance(data, str):
            return self._expand_string(data)
        return data

    def _expand_string(self, value: str) -> str:
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            if var_name in self._env:
                return self._env[var_name]
            if default is not None:
                return default[2:]
            raise ConfigValidationException(
                f"unresolved config variable: {var_name}",
                code="CONFIG_UNRESOLVED_VARIABLE",
            )

        return _VAR_PATTERN.sub(_replace, value)

    def _resolve_secrets(self, data: dict[str, Any]) -> dict[str, Any]:
        # Sprint 1 pass-through stub — see SPRINT_1_STATUS.md.
        return data

    def _fingerprint(self, data: dict[str, Any]) -> str:
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
