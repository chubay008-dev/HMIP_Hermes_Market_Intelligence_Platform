"""market_overview.py — Đọc dữ liệu thị trường bia VN (thị phần + xu hướng).

Nguồn: knowledge/master/market_share.json + trends.json (research web thực tế).
KHÔNG phải data ảo. Dùng cho dashboard tab Workspace (section Thị trường).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_MASTER_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "master"
_cache: dict[str, Any] = {}


def _load_raw() -> dict[str, Any]:
    global _cache
    if _cache:
        return _cache
    out: dict[str, Any] = {}
    for f, key in (("market_share.json", "share"), ("trends.json", "trends")):
        p = _MASTER_DIR / f
        if p.exists():
            try:
                out[key] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                out[key] = {}
    _cache = out
    return _cache


def get_market_overview() -> dict[str, Any]:
    """Trả thị phần + xu hướng bia VN cho dashboard."""
    raw = _load_raw()
    share = raw.get("share", {})
    trends = raw.get("trends", {})
    return {
        "meta": share.get("meta", {}),
        "total_volume_liter": share.get("total_volume_2024_liter"),
        "by_brand": share.get("by_brand", []),
        "by_segment": share.get("by_segment", []),
        "top4_concentration_pct": share.get("top4_concentration_pct"),
        "key_facts": share.get("key_facts", []),
        "trends": trends.get("trends", []),
        "trends_summary": trends.get("summary", ""),
    }


def reload() -> None:
    global _cache
    _cache = {}
