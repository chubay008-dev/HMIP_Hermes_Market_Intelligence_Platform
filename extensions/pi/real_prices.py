"""real_prices.py — Đọc bảng giá bia THẬT thị trường VN.

Nguồn: knowledge/master/prices_real.json (được làm giàu bởi research web
thực tế: Tiki API + LotteMart/BachHoaXanh/Emart/websosanh/importers).
KHÔNG phải data ảo (seed). Dùng cho dashboard cột "giá thật" và so sánh
với giá quét.

Schema prices_real.json:
  meta: {description, currency, captured_date, sources, count}
  prices: [ {product_id, name, pack_case, price_case_vnd,
             price_single_vnd, source, confidence, note, captured_date} ]
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("hmip.real_prices")

_MASTER_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "master"
_PRICES_FILE = _MASTER_DIR / "prices_real.json"

_cache: dict[str, Any] = {}


def _load_raw() -> dict[str, Any]:
    global _cache
    if _cache:
        return _cache
    if not _PRICES_FILE.exists():
        log.warning("Thiếu %s — trả giá thật rỗng", _PRICES_FILE)
        _cache = {"meta": {}, "prices": []}
        return _cache
    try:
        _cache = json.loads(_PRICES_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Lỗi đọc %s: %s", _PRICES_FILE, exc)
        _cache = {"meta": {}, "prices": []}
    return _cache


def get_real_prices() -> list[dict[str, Any]]:
    """Toàn bộ bảng giá thật (list of price records)."""
    return _load_raw().get("prices", [])


def get_real_price_map() -> dict[str, dict[str, Any]]:
    """{product_id: price_record} để lookup O(1).

    Mỗi record có thể có trường 'channels' (dict kênh->giá) để so sánh
    đa kênh, và 'best_channel' (kênh rẻ nhất).
    """
    return {p["product_id"]: p for p in get_real_prices()}


def get_channel_comparison() -> dict[str, Any]:
    """Bảng so sánh giá đa kênh (Channel Comparison) từ giá thật.

    Trả: {captured_date, channels: [tên kênh], products: [{
        product_id, name, best_channel, best_case_vnd,
        by_channel: {kênh: {case_vnd, single_vnd, confidence}}
    }]}.
    Chỉ gồm SKU có dữ liệu channels (đa kênh). Nếu SKU chỉ có 1 nguồn,
    by_channel chứa nguồn đó (coi như 1 kênh).
    """
    raw = _load_raw()
    meta = raw.get("meta", {})
    products = []
    ch_set: set[str] = set()
    for p in raw.get("prices", []):
        ch = p.get("channels")
        if ch:
            by_channel = ch
            ch_set.update(ch.keys())
        else:
            # single source -> 1 kênh
            src = p.get("source", "web")
            by_channel = {src: {
                "case_vnd": p.get("price_case_vnd"),
                "single_vnd": p.get("price_single_vnd"),
                "confidence": p.get("confidence", "medium"),
            }}
            ch_set.add(src)
        # tìm kênh rẻ nhất (theo case_vnd)
        valid = {k: v for k, v in by_channel.items() if v.get("case_vnd")}
        best = min(valid, key=lambda k: valid[k]["case_vnd"]) if valid else None
        products.append({
            "product_id": p["product_id"],
            "name": p.get("name") or p["product_id"],
            "best_channel": best,
            "best_case_vnd": valid[best]["case_vnd"] if best else None,
            "by_channel": by_channel,
        })
    return {
        "captured_date": meta.get("captured_date"),
        "channels": sorted(ch_set),
        "products": products,
    }


def get_meta() -> dict[str, Any]:
    return _load_raw().get("meta", {})


def reload() -> None:
    """Xóa cache để lần đọc sau lấy file mới nhất."""
    global _cache
    _cache = {}


if __name__ == "__main__":
    m = get_real_price_map()
    print(f"Đã load {len(m)} giá thật. VD:")
    for pid in ("P456", "P789", "PTBG"):
        if pid in m:
            r = m[pid]
            print(f"  {pid}: thùng={r['price_case_vnd']:,}₫ lẻ={r['price_single_vnd']:,}₫ ({r['source']})")
