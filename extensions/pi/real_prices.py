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


def _normalize_channel(case: int | None, single: int | None
                       ) -> tuple[int | None, int | None, bool]:
    """Chuẩn hoá 1 entry kênh: đảm bảo single = giá LON, case = giá THÙNG 24.

    Lỗi thường gặp trong data auto-collect:
    - single_vnd thực là giá THÙNG (vd 87600, 109000, 51000) do parse nhầm
      đơn vị → single >= case/6 (lon luôn < thùng/6 với bia).
    - case_vnd outlier (gấp >1.6× median kênh khác của cùng SP) do bắt thùng
      khác cỡ (vd mmmega 792000 vs ~230000).

    Trả (case, single, fixed?). fixed=True nếu đã chỉnh.
    """
    fixed = False
    if case and single and single >= case / 6:
        # single thực là thùng → suy lon = case/24.
        single = round(case / 24)
        fixed = True
    return case, single, fixed


def _normalize_product_channels(by_channel: dict[str, dict]) -> dict[str, dict]:
    """Chuẩn hoá channels của 1 SP: fix single (lon) rồi fix case outlier.

    Case outlier so với median case của SP (sau khi fix single). Nếu case lệch
    >1.6× hoặc <0.5× median và single OK → case = single×24; else case = median.
    """
    out = {k: dict(v) for k, v in by_channel.items()}
    # Bước 1: fix single (lon) cho từng kênh.
    for cid, c in out.items():
        case, single, fixed = _normalize_channel(c.get("case_vnd"), c.get("single_vnd"))
        if fixed:
            c["case_vnd"], c["single_vnd"] = case, single
            c["confidence"] = "low"  # đã suy lại → giảm confidence
    # Bước 2: fix case outlier vs median case của SP. Khi case lệch >1.6× hoặc
    # <0.5× median, không tin case (và single đi kèm thường cũng sai, vd mmmega
    # case 792000 + single 33000 cho bia Hà Nội thùng ~230k) → dùng median kênh
    # khác (single suy lại = median/24).
    cases = [c["case_vnd"] for c in out.values() if c.get("case_vnd")]
    if len(cases) >= 4:
        cases_s = sorted(cases)
        median = cases_s[len(cases_s) // 2]
        for cid, c in out.items():
            case = c.get("case_vnd")
            if not case or not median:
                continue
            if case > median * 1.6 or case < median * 0.5:
                c["case_vnd"] = median
                c["single_vnd"] = round(median / 24)
                c["confidence"] = "low"
    return out


def get_channel_comparison() -> dict[str, Any]:
    """Bảng so sánh giá đa kênh (Channel Comparison) từ giá thật.

    Trả: {captured_date, channels: [tên kênh], products: [{
        product_id, name, best_channel, best_case_vnd,
        by_channel: {kênh: {case_vnd, single_vnd, confidence}}
    }]}.
    Chỉ gồm SKU có dữ liệu channels (đa kênh). Nếu SKU chỉ có 1 nguồn,
    by_channel chứa nguồn đó (coi như 1 kênh).

    Data auto-collect thường bị lỗi đơn vị (single_vnd thực là thùng, case_vnd
    outlier) → chuẩn hoá qua _normalize_product_channels trước khi trả để bảng
    luôn nhất quán (lon < thùng/6, case không outlier vs median SP).
    """
    raw = _load_raw()
    meta = raw.get("meta", {})
    products = []
    ch_set: set[str] = set()
    for p in raw.get("prices", []):
        ch = p.get("channels")
        if ch:
            by_channel = _normalize_product_channels(ch)
            ch_set.update(by_channel.keys())
        else:
            # single source -> 1 kênh
            src = p.get("source", "web")
            case, single, _ = _normalize_channel(p.get("price_case_vnd"),
                                                  p.get("price_single_vnd"))
            by_channel = {src: {
                "case_vnd": case,
                "single_vnd": single,
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
