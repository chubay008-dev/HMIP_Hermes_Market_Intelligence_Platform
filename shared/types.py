"""Shared reusable type aliases."""

from __future__ import annotations

from typing import Any

JSONObject = dict[str, Any]
JSONValue = JSONObject | list[Any] | str | int | float | bool | None
