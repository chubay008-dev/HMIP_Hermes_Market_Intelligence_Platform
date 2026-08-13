"""seed.py — Sinh dữ liệu market thực tế cho HMIP Price Intelligence.

Dùng catalog 48 bia từ extensions.default_products (giữ nguyên nguyên
tắc "hardcode full catalog để mỗi deploy tái lập được"). Sinh:
  * 48 sản phẩm × 5 kênh × 5 vùng × N ngày lịch sử
  * Mean-reverting quanh base (giá bia sideway, ít biến động)
  * Một vài "price event" thực sự (bước nhảy 6-15%) cho events/alerts
  * Promotion định kỳ (Flash Sale cuối tuần, campaign theo mùa)

QUAN TRỌNG: events được INSERT TRỰC TIẾP tại các jump_day đã biết
(không detect mò trên noise) → events sạch, có ý nghĩa, không nhiễu.
Tất cả ghi vào DB PI riêng (không đụng DB cũ). Idempotent.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from extensions.default_products import DEFAULT_PRODUCTS
from extensions.pi import normalization, pi_store
from extensions.pi.models import DEFAULT_THRESHOLDS, Severity, now_iso

# ---------------------------------------------------------------------------
# Static dimensions
# ---------------------------------------------------------------------------
CHANNELS: dict[str, tuple[str, str]] = {
    "SHOPEE": ("Shopee", "ecommerce"),
    "LAZADA": ("Lazada", "ecommerce"),
    "TIKI": ("Tiki", "ecommerce"),
    "WINMART": ("WinMart", "modern_trade"),
    "AEON": ("AEON", "modern_trade"),
}
REGIONS: dict[str, tuple[str, str, str]] = {
    "HCMC": ("VN", "South", "TP.HCM"),
    "HANOI": ("VN", "North", "Hà Nội"),
    "DANANG": ("VN", "Central", "Đà Nẵng"),
    "CANTHO": ("VN", "Mekong", "Cần Thơ"),
    "HAIPHONG": ("VN", "North", "Hải Phòng"),
}
_CHANNEL_FACTOR = {
    "SHOPEE": 0.93, "LAZADA": 0.94, "TIKI": 0.95,
    "WINMART": 1.04, "AEON": 1.02,
}
_REGION_FACTOR = {
    "HCMC": 1.00, "HANOI": 1.01, "DANANG": 0.99,
    "CANTHO": 0.98, "HAIPHONG": 1.00,
}
_DEFAULT_PACK = {"quantity": 24, "volume_ml": 330.0}
_PACK_OVERRIDES: dict[str, tuple[float, float]] = {
    "440": (24, 440.0),
    "500": (24, 500.0),
    "640": (12, 640.0),
}


def _parse_pack(product_name: str, ref_price: float) -> tuple[float, float]:
    name_upper = product_name.upper()
    for key, (q, v) in _PACK_OVERRIDES.items():
        if key in name_upper:
            return q, v
    if "640ML" in name_upper:
        return 12, 640.0
    if "500ML" in name_upper:
        return 24, 500.0
    if "440ML" in name_upper:
        return 24, 440.0
    return _DEFAULT_PACK["quantity"], _DEFAULT_PACK["volume_ml"]


def _brand_id(product_id: str, brand: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in brand)
    return f"BR-{safe}"


def seed_full(history_days: int = 90, path: str | None = None,
              seed: int = 20260812) -> dict[str, Any]:
    """Xoá và seed lại toàn bộ dữ liệu PI. Trả summary."""
    rng = random.Random(seed)
    init = pi_store
    init.init_pi_db(path)

    # Reset tables (idempotent seed)
    # Tắt FK check khi xóa để tránh IntegrityError do thứ tự bảng
    conn = init._connect(path or init.DEFAULT_PI_DB_PATH)  # type: ignore[attr-defined]
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        for t in ("pi_observations", "pi_promotions", "pi_price_events",
                  "pi_alerts", "pi_ai_analyses", "pi_skus", "pi_products",
                  "pi_brands", "pi_categories", "pi_channels", "pi_regions",
                  "pi_sellers"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()

    # Static dimensions
    init.upsert_category("BEER", "Beer & Beverage", path=path)
    for cid, (name, ctype) in CHANNELS.items():
        init.upsert_channel(cid, name, ctype, path=path)
    for rid, (country, region, province) in REGIONS.items():
        init.upsert_region(rid, country, region, province, city=province, path=path)
    for cid in CHANNELS:
        for rid in REGIONS:
            sid = f"SELLER-{cid}-{rid}"
            init.upsert_seller(
                sid, f"{CHANNELS[cid][0]} {REGIONS[rid][2]} Store",
                seller_type=CHANNELS[cid][1], verification_status="verified", path=path)

    n_obs = 0
    n_promo = 0
    n_events = 0
    n_alerts = 0
    products_meta: list[dict[str, Any]] = []
    obs_rows: list[dict[str, Any]] = []
    promo_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    alert_rows: list[dict[str, Any]] = []

    end_date = datetime(2026, 8, 12, tzinfo=timezone.utc)
    start_date = end_date - timedelta(days=history_days)
    thresholds = DEFAULT_THRESHOLDS

    for pid, meta in DEFAULT_PRODUCTS.items():
        brand = str(meta["brand"])
        pname = str(meta["product_name"])
        ref = float(meta["ref_price"])
        bid = _brand_id(pid, brand)
        qty, vol = _parse_pack(pname, ref)
        sku_id = f"SKU-{pid}"
        init.upsert_brand(bid, brand, path=path)
        init.upsert_product(pid, bid, "BEER", pname, variant=None,
                            pack_size=f"{int(vol)}ml x{int(qty)}",
                            volume_ml=vol, unit="can", path=path)
        init.upsert_sku(sku_id, pid, barcode=f"893{abs(hash(pid)) % 10**9:09d}"[:13],
                        pack_quantity=qty, unit_volume_ml=vol,
                        normalized_unit="per_100ml", path=path)
        products_meta.append({"product_id": pid, "brand_id": bid, "sku_id": sku_id,
                              "name": pname, "brand": brand, "ref_price": ref,
                              "qty": qty, "vol": vol})

        # ~30% sản phẩm có 1 bước nhảy "event" thực sự trong lịch sử
        jump_day = (rng.randint(10, max(11, history_days - 3))
                    if (rng.random() < 0.30 and history_days > 12) else None)
        jump_sign = 1 if rng.random() < 0.5 else -1
        jump_pct = rng.uniform(0.06, 0.15)

        for cid in CHANNELS:
            cf = _CHANNEL_FACTOR.get(cid, 1.0)
            for rid in REGIONS:
                rf = _REGION_FACTOR.get(rid, 1.0)
                base = ref * cf * rf
                price = base
                prev_price = base
                day = 0
                while day < history_days:
                    cur_date = start_date + timedelta(days=day)
                    # Mean-reverting mạnh về base (giá bia sideway).
                    shock = rng.gauss(0, 0.0015) * base
                    price = base + (price - base) * 0.6 + shock
                    if jump_day is not None and day == jump_day:
                        new_after = price * (1 + jump_sign * jump_pct)
                        if prev_price > 0:
                            chg = (new_after - prev_price) / prev_price * 100.0
                            etype = "PRICE_INCREASE" if chg > 0 else "PRICE_DECREASE"
                            sev = (Severity.CRITICAL if abs(chg) >= thresholds["high"]
                                   else Severity.HIGH if abs(chg) >= thresholds["medium"]
                                   else Severity.MEDIUM)
                            dk = f"{sku_id}|{cid}|{rid}|{etype}|{cur_date.date()}"
                            ev_id = f"PE-{cur_date.date().isoformat().replace('-', '')}-{sku_id}-{cid}-{rid}"
                            event_rows.append({
                                "event_id": ev_id, "sku_id": sku_id, "channel_id": cid,
                                "region_id": rid, "timestamp": cur_date.isoformat(),
                                "old_price": round(prev_price, 2),
                                "new_price": round(new_after, 2),
                                "change_percent": round(chg, 2), "event_type": etype,
                                "significance": "HIGH" if abs(chg) >= thresholds["high"] else "MEDIUM",
                                "confidence": 0.95, "dedup_key": dk,
                            })
                            n_events += 1
                            if sev == Severity.CRITICAL:
                                alert_rows.append({
                                    "alert_id": f"AL-{ev_id}", "event_id": ev_id,
                                    "sku_id": sku_id, "severity": sev,
                                    "created_at": now_iso(),
                                    "message": (f"{'Tăng' if chg > 0 else 'Giảm'} giá {sku_id} "
                                                f"{abs(chg):.1f}% trên {cid} ({rid}). Mức {sev}."),
                                    "dedup_key": dk,
                                })
                                n_alerts += 1
                        price = new_after
                    price = max(price, base * 0.6)

                    is_weekend = cur_date.weekday() >= 5
                    promo = None
                    if is_weekend and rng.random() < 0.55:
                        promo = rng.uniform(0.05, 0.18)
                    elif rng.random() < 0.10:
                        promo = rng.uniform(0.03, 0.10)

                    regular = round(price, -2)
                    promo_price = round(regular * (1 - promo), -2) if promo is not None else None
                    eff = promo_price if promo_price else regular
                    norm = normalization.normalize_price(
                        regular_price=regular, pack_quantity=qty, unit_volume_ml=vol,
                        promotion_price=promo_price, effective_price=eff)
                    obs_rows.append({
                        "observation_id": f"OBS-{pid}-{cid}-{rid}-{day}",
                        "sku_id": sku_id, "product_id": pid, "brand_id": bid,
                        "channel_id": cid, "seller_id": f"SELLER-{cid}-{rid}",
                        "region_id": rid, "observed_at": cur_date.isoformat(),
                        "collected_at": (cur_date + timedelta(minutes=rng.randint(0, 59))).isoformat(),
                        "regular_price": regular, "effective_price": eff,
                        "promotion_price": promo_price, "currency": "VND",
                        "unit_price": norm.price_per_unit, "normalized_price": norm.price_per_100ml,
                        "availability": "in_stock", "source": CHANNELS[cid][0],
                        "source_url": f"https://{cid.lower()}.vn/p/{pid}",
                        "extraction_method": "seed_simulator", "confidence": 0.92,
                        "metadata": None,
                    })
                    n_obs += 1
                    if promo_price:
                        n_promo += 1
                        ptype = "Flash Sale" if is_weekend else "Campaign"
                        promo_rows.append({
                            "promotion_id": f"PRM-{pid}-{cid}-{rid}-{day}",
                            "sku_id": sku_id, "channel_id": cid,
                            "seller_id": f"SELLER-{cid}-{rid}", "region_id": rid,
                            "start_time": cur_date.isoformat(),
                            "end_time": (cur_date + timedelta(days=2)).isoformat(),
                            "regular_price": regular, "promotion_price": promo_price,
                            "discount_percent": round((promo or 0) * 100, 2),
                            "promotion_type": ptype,
                            "campaign": f"{ptype} {cur_date.strftime('%Y-%m')}",
                            "source_url": f"https://{cid.lower()}.vn/p/{pid}",
                        })
                    prev_price = price
                    day += 1

    # Bulk insert (1 session) — rất nhanh
    init.bulk_insert_observations(obs_rows, path=path)
    init.bulk_insert_promotions(promo_rows, path=path)
    init.bulk_insert_events(event_rows, path=path)
    init.bulk_insert_alerts(alert_rows, path=path)

    return {
        "status": "seeded", "products": len(products_meta),
        "channels": len(CHANNELS), "regions": len(REGIONS),
        "observations": n_obs, "promotions": n_promo,
        "events": n_events, "alerts": n_alerts,
        "history_days": history_days,
        "db_path": pi_store.db_path_resolved(path),
    }
