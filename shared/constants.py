"""Shared constants used across HMIP modules."""

from __future__ import annotations

import importlib.metadata

DEFAULT_CONFIG_ENCODING = "utf-8"


def _resolve_runtime_version() -> str:
    """RUNTIME_VERSION is tied to the real package version declared in
    pyproject.toml (project decision, resolving the placeholder-value
    open question tracked since SPRINT_3_STATUS.md) rather than a
    second, hand-maintained constant that could drift from it. Falls
    back to a hardcoded value only if the package's metadata isn't
    discoverable (e.g. running from a raw source checkout without
    `pip install -e .`)."""
    try:
        return importlib.metadata.version("hmip")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


RUNTIME_VERSION = _resolve_runtime_version()

# Kernel version is this codebase's own release train for core/
# runtime kernel behavior specifically — separate from the
# pyproject.toml package version, bumped manually whenever kernel
# behavior changes in a way worth tracking. Starts at 1.0.0 (project
# decision) marking the first working kernel, once the interface
# contract retrofit (see SPRINT_3_STATUS.md) landed.
KERNEL_VERSION = "1.0.0"

# Mirrors core.models decision constants for callers that only need the
# string values without importing the dataclass module.
DECISION_IGNORE = "IGNORE"
DECISION_ALERT = "ALERT"
DECISION_ESCALATE = "ESCALATE"
DECISION_HUMAN_REVIEW = "HUMAN_REVIEW"
