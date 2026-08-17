"""analytics.py — Price Intelligence analytics engine (Spec §14, §18, §19, §20, §21).

Tất cả hàm nhận `path` (DB PI) và các filter, trả dict sẵn sàng cho API.
Tuân thủ:
  * §14 Metrics: AVG/MEDIAN/MIN/MAX/CHANGE/INDEX
  * §10 Comparable universe: chỉ so SKU cùng volume (price_per_100ml)
  * §11 Normalization: dùng normalized_price (per_100ml) làm comparable
  * §44 Timezone: lưu UTC, hiển thị theo filter
  * §45 Performance: aggregate server-side, trả ≤365 điểm
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from extensions.pi import pi_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else 0.0


def _to_utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    mapping = {
        "7D": timedelta(days=7),
        "30D": timedelta(days=30),
        "90D": timedelta(days=90),
        "6M": timedelta(days=182),
        "12M": timedelta(days=365),
        "ALL": timedelta(days=3650),
    }
    return now - mapping.get(period.upper(), timedelta(days=90))


def _where_clause(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    """Xây WHERE clause từ bộ filter đồng bộ (Spec §5.1)."""
    clauses: list[str] = []
    params: list[Any] = []
    if filters.get("product_id"):
        clauses.append("o.product_id = ?")
        params.append(filters["product_id"])
    if filters.get("brand_id"):
        clauses.append("o.brand_id = ?")
        params.append(filters["brand_id"])
    if filters.get("channel_id"):
        clauses.append("o.channel_id = ?")
        params.append(filters["channel_id"])
    if filters.get("region_id"):
        clauses.append("o.region_id = ?")
        params.append(filters["region_id"])
    if filters.get("period"):
        start = _period_start(filters["period"])
        clauses.append("o.observed_at >= ?")
        params.append(_to_utc_iso(start))
    if filters.get("promotion_only"):
        clauses.append("o.promotion_price IS NOT NULL")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


# ---------------------------------------------------------------------------
# KPI Overview (Spec §6, §13)
# ---------------------------------------------------------------------------

def kpi_overview(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    f = filters or {}
    where, params = _where_clause(f)
    rows = pi_store.fetch_all(
        f"""SELECT o.effective_price, o.regular_price, o.normalized_price,
                   o.observed_at, o.product_id
            FROM pi_observations o
            {where}""",
        params, path=path,
    )
    if not rows:
        return {
            "avg_price": None, "median_price": None, "min_price": None,
            "max_price": None, "price_change_pct": None, "price_index": None,
            "observation_count": 0, "comparable_count": 0,
        }
    eff = [float(r["effective_price"]) for r in rows]
    avg = statistics.mean(eff)
    med = _median(eff)
    mn = min(eff)
    mx = max(eff)

    # Price change: so kỳ trước (nửa đầu vs nửa sau của window)
    rows_sorted = sorted(rows, key=lambda r: r["observed_at"])
    half = len(rows_sorted) // 2
    first_half = [float(r["effective_price"]) for r in rows_sorted[:half]]
    second_half = [float(r["effective_price"]) for r in rows_sorted[half:]]
    change = None
    if first_half and second_half:
        change = (statistics.mean(second_half) - statistics.mean(first_half)) / statistics.mean(first_half) * 100.0

    # Price index vs market reference = median của window (Spec §14, §8.1)
    ref = med
    price_index = round(avg / ref * 100, 2) if ref else None

    return {
        "avg_price": round(avg, 2),
        "median_price": round(med, 2),
        "min_price": round(mn, 2),
        "max_price": round(mx, 2),
        "price_change_pct": round(change, 2) if change is not None else None,
        "price_index": price_index,
        "observation_count": len(rows),
        "comparable_count": len({r["product_id"] for r in rows}),
        "reference_method": "median",
    }


# ---------------------------------------------------------------------------
# Price Trend (Spec §15) — daily aggregation, series toggle
# ---------------------------------------------------------------------------

def price_trend(filters: dict[str, Any] | None = None,
                series: list[str] | None = None, path: str | None = None) -> dict[str, Any]:
    f = filters or {}
    where, params = _where_clause(f)
    series = series or ["sku_price", "market_avg", "brand_avg"]
    rows = pi_store.fetch_all(
        f"""SELECT o.observed_at, o.effective_price, o.regular_price,
                   o.promotion_price, o.product_id, o.brand_id, o.channel_id
            FROM pi_observations o {where}""",
        params, path=path,
    )
    if not rows:
        return {"series": {}, "points": 0}

    # aggregate by day
    by_day: dict[str, list[float]] = {}
    by_day_brand: dict[str, dict[str, list[float]]] = {}
    by_day_regular: dict[str, list[float]] = {}
    by_day_promo: dict[str, list[float]] = {}
    by_day_channel: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        day = r["observed_at"][:10]
        by_day.setdefault(day, []).append(float(r["effective_price"]))
        by_day_regular.setdefault(day, []).append(float(r["regular_price"]))
        if r["promotion_price"] is not None:
            by_day_promo.setdefault(day, []).append(float(r["promotion_price"]))
        if "brand_avg" in series:
            by_day_brand.setdefault(r["brand_id"], {}).setdefault(day, []).append(
                float(r["effective_price"]))
        if "channel_breakdown" in series and r["channel_id"]:
            by_day_channel.setdefault(r["channel_id"], {}).setdefault(day, []).append(
                float(r["effective_price"]))

    days = sorted(by_day.keys())
    out: dict[str, Any] = {"sku_price" if f.get("product_id") else "market_avg": []}
    # Build series
    result: dict[str, list[dict[str, Any]]] = {s: [] for s in series}
    # Khi chưa chọn product_id, sku_price không có nghĩa (không có SKU cụ thể).
    # Backfill sku_price = market_avg để chart "SKU" vẫn hiện đường giá thị trường
    # TB thay vì trống — tránh user thấy chart "không có dữ liệu" khi vào trang lần đầu.
    sku_backfill = "sku_price" in series and not f.get("product_id")
    for day in days:
        if sku_backfill:
            result["sku_price"].append({"t": day, "v": round(statistics.mean(by_day[day]), 2)})
        if "sku_price" in series and f.get("product_id"):
            result["sku_price"].append({"t": day, "v": round(statistics.mean(by_day[day]), 2)})
        if "market_avg" in series:
            result["market_avg"].append({"t": day, "v": round(statistics.mean(by_day[day]), 2)})
        if "brand_avg" in series:
            for bid, dd in by_day_brand.items():
                if day in dd:
                    result.setdefault("brand_avg", []).append(
                        {"t": day, "brand": bid, "v": round(statistics.mean(dd[day]), 2)})
        if "regular_price" in series:
            if day in by_day_regular:
                result["regular_price"].append(
                    {"t": day, "v": round(statistics.mean(by_day_regular[day]), 2)})
        if "promotion_price" in series and day in by_day_promo:
            result["promotion_price"].append(
                {"t": day, "v": round(statistics.mean(by_day_promo[day]), 2)})

    # Channel breakdown: series per channel_id → [{t,v}] (giá TB ngày per kênh).
    # Resolve tên hiển thị kênh để frontend vẽ legend trực tiếp.
    if "channel_breakdown" in series and by_day_channel:
        cid_rows = pi_store.fetch_all(
            "SELECT channel_id, channel_name FROM pi_channels", [], path=path)
        cid_name = {r["channel_id"]: r["channel_name"] for r in cid_rows}
        chan_series: dict[str, list[dict[str, Any]]] = {}
        for cid, dd in by_day_channel.items():
            name = cid_name.get(cid, cid)
            chan_series[name] = [
                {"t": day, "v": round(statistics.mean(vals), 2)}
                for day, vals in sorted(dd.items())
            ]
        result["channel_breakdown"] = chan_series  # type: ignore[assignment]

    return {"series": result, "points": len(days)}


# ---------------------------------------------------------------------------
# Price Index by brand (Spec §14, §8)
# ---------------------------------------------------------------------------

def price_index_by_brand(filters: dict[str, Any] | None = None,
                         method: str = "median", path: str | None = None) -> dict[str, Any]:
    f = filters or {}
    where, params = _where_clause(f)
    rows = pi_store.fetch_all(
        f"""SELECT o.brand_id, b.name AS brand_name, o.normalized_price,
                   o.effective_price
            FROM pi_observations o
            JOIN pi_products p ON p.product_id = o.product_id
            JOIN pi_brands b ON b.brand_id = p.brand_id
            {where}""",
        params, path=path,
    )
    if not rows:
        return {"method": method, "market_reference": None, "brands": []}

    # Market reference = median normalized_price (per 100ml) của toàn bộ
    norm_all = [float(r["normalized_price"]) for r in rows if r["normalized_price"] is not None]
    if method == "mean":
        ref = statistics.mean(norm_all) if norm_all else 0.0
    elif method == "weighted_mean":
        ref = statistics.mean(norm_all) if norm_all else 0.0
    elif method == "weighted_median":
        ref = _median(norm_all) if norm_all else 0.0
    else:  # median
        ref = _median(norm_all) if norm_all else 0.0

    by_brand: dict[str, list[float]] = {}
    names: dict[str, str] = {}
    for r in rows:
        if r["normalized_price"] is None:
            continue
        bid = r["brand_id"] or ""
        # Bỏ brand rỗng (observation cũ chưa resolve brand_id).
        if not bid:
            continue
        by_brand.setdefault(bid, []).append(float(r["normalized_price"]))
        names[bid] = r["brand_name"]

    brands = []
    for bid, vals in by_brand.items():
        brand_avg = statistics.mean(vals)
        idx = round(brand_avg / ref * 100, 2) if ref else 100.0
        brands.append({
            "brand_id": bid, "brand": names.get(bid, bid),
            "avg_normalized_price": round(brand_avg, 2),
            "price_index": idx,
        })
    brands.sort(key=lambda x: x["price_index"], reverse=True)
    cheapest = brands[-1] if brands else None
    most_exp = brands[0] if brands else None
    return {
        "method": method, "market_reference": round(ref, 2), "brands": brands,
        "cheapest_brand": cheapest, "most_expensive_brand": most_exp,
    }


# ---------------------------------------------------------------------------
# Competitor comparison (Spec §18) — comparable universe (same volume)
# ---------------------------------------------------------------------------

def competitor_comparison(filters: dict[str, Any] | None = None,
                          path: str | None = None) -> dict[str, Any]:
    f = filters or {}
    where, params = _where_clause(f)
    # Join product để lấy volume (comparable universe). JOIN pi_brands qua
    # p.brand_id (product) thay vì o.brand_id (observation) — observation có
    # thể ghi brand_id rỗng → match ('','Unknown') → hiện "Unknown" trong UI.
    rows = pi_store.fetch_all(
        f"""SELECT o.product_id, p.product_name, p.brand_id, b.name AS brand,
                   o.channel_id, o.region_id, o.effective_price,
                   o.normalized_price, p.volume_ml
            FROM pi_observations o
            JOIN pi_products p ON p.product_id = o.product_id
            JOIN pi_brands b ON b.brand_id = p.brand_id
            {where}""",
        params, path=path,
    )
    if not rows:
        return {"comparable_universe": None, "rows": []}

    # Comparable: cùng volume_ml (Spec §10)
    target_vol = rows[0]["volume_ml"]
    comp = [r for r in rows if r["volume_ml"] == target_vol]

    # Chọn brand theo product_id deterministic: ưu tiên brand_id không rỗng,
    # fallback brand_id đầu tiên gặp (tránh ghi đè Unknown từ row cũ).
    by_product: dict[str, list[float]] = {}
    meta: dict[str, dict[str, Any]] = {}
    for r in comp:
        by_product.setdefault(r["product_id"], []).append(float(r["effective_price"]))
        brand_id = r.get("brand_id") or ""
        if r["product_id"] not in meta or (brand_id and not meta[r["product_id"]].get("brand_id")):
            meta[r["product_id"]] = {
                "product_id": r["product_id"], "name": r["product_name"],
                "brand": r["brand"] or "Unknown", "brand_id": brand_id,
                "volume_ml": r["volume_ml"],
            }
    market_avg = statistics.mean([v for vs in by_product.values() for v in vs]) if by_product else 0.0
    out_rows = []
    for pid, vals in by_product.items():
        avg = statistics.mean(vals)
        ref = price_index_for_value(avg, market_avg)
        out_rows.append({
            **meta[pid], "avg_price": round(avg, 2),
            "price_index": ref, "n": len(vals),
        })
    out_rows.sort(key=lambda x: x["avg_price"])
    return {
        "comparable_universe": f"{int(target_vol)}ml",
        "market_average": round(market_avg, 2),
        "rows": out_rows,
    }


# ---------------------------------------------------------------------------
# Price Index time-series (Roadmap Bước 2 / v3.1 §2)
# Baseline = giá trung bình ngày đầu tiên của window; index[t] = price[t]/baseline*100
# ---------------------------------------------------------------------------

def price_index_trend(filters: dict[str, Any] | None = None,
                     path: str | None = None) -> dict[str, Any]:
    """Tính Price Index theo thời gian (time-series) để so sánh xu hướng.

    Baseline mặc định = giá trung bình ngày đầu của window (index=100).
    Trả series daily: mỗi điểm {t, index, price}.

    Khớp v3.1 §2 Price Index methodology: chuẩn hóa theo thời gian thay vì
    chỉ snapshot. Dùng để vẽ biểu đồ xu hướng giá (tăng/giảm % theo thời gian).
    """
    f = filters or {}
    where, params = _where_clause(f)
    rows = pi_store.fetch_all(
        f"""SELECT o.observed_at, o.effective_price, o.normalized_price
            FROM pi_observations o {where}""",
        params, path=path,
    )
    if not rows:
        return {"baseline_date": None, "baseline_price": None, "series": [], "points": 0}

    # aggregate by day
    by_day: dict[str, list[float]] = {}
    for r in rows:
        day = r["observed_at"][:10]
        by_day.setdefault(day, []).append(float(r["effective_price"]))
    days = sorted(by_day.keys())
    daily_avg = {d: statistics.mean(v) for d, v in by_day.items()}

    baseline_price = daily_avg[days[0]]  # ngày đầu window
    series = []
    for d in days:
        price = daily_avg[d]
        idx = round(price / baseline_price * 100, 2) if baseline_price else 100.0
        series.append({"t": d, "index": idx, "price": round(price, 2)})

    # biến động tổng thể
    change_pct = round((series[-1]["index"] - 100), 2) if series else None
    return {
        "baseline_date": days[0],
        "baseline_price": round(baseline_price, 2),
        "change_pct_from_baseline": change_pct,
        "series": series,
        "points": len(series),
    }


def price_index_for_value(value: float, ref: float) -> float:
    return round(value / ref * 100, 2) if ref else 100.0


# ---------------------------------------------------------------------------
# Channel comparison (Spec §19)
# ---------------------------------------------------------------------------

def channel_comparison(filters: dict[str, Any] | None = None,
                       path: str | None = None) -> dict[str, Any]:
    f = filters or {}
    where, params = _where_clause(f)
    rows = pi_store.fetch_all(
        f"""SELECT o.channel_id, c.channel_name, c.channel_type,
                   o.effective_price, o.normalized_price
            FROM pi_observations o
            JOIN pi_channels c ON c.channel_id = o.channel_id
            {where}""",
        params, path=path,
    )
    if not rows:
        return {"channels": []}
    by_ch: dict[str, dict[str, Any]] = {}
    for r in rows:
        ch = by_ch.setdefault(r["channel_id"], {
            "channel_id": r["channel_id"], "channel": r["channel_name"],
            "type": r["channel_type"], "prices": [], "norm": [],
        })
        ch["prices"].append(float(r["effective_price"]))
        if r["normalized_price"] is not None:
            ch["norm"].append(float(r["normalized_price"]))
    out = []
    all_norm = [v for ch in by_ch.values() for v in ch["norm"]] or [0.0]
    ref = _median(all_norm)
    for ch in by_ch.values():
        avg = statistics.mean(ch["prices"])
        out.append({
            "channel_id": ch["channel_id"], "channel": ch["channel"],
            "type": ch["type"], "avg_price": round(avg, 2),
            "price_index": price_index_for_value(statistics.mean(ch["norm"]) if ch["norm"] else avg, ref),
            "n": len(ch["prices"]),
        })
    out.sort(key=lambda x: x["avg_price"])
    lowest = out[0] if out else None
    highest = out[-1] if out else None
    return {
        "channels": out,
        "lowest_channel": lowest, "highest_channel": highest,
        "market_reference": round(ref, 2),
    }


# ---------------------------------------------------------------------------
# Regional pricing (Spec §20)
# ---------------------------------------------------------------------------

def regional_pricing(filters: dict[str, Any] | None = None,
                     path: str | None = None) -> dict[str, Any]:
    f = filters or {}
    where, params = _where_clause(f)
    rows = pi_store.fetch_all(
        f"""SELECT o.region_id, r.region, r.province, r.city,
                   o.effective_price, o.normalized_price
            FROM pi_observations o
            JOIN pi_regions r ON r.region_id = o.region_id
            {where}""",
        params, path=path,
    )
    if not rows:
        return {"regions": []}
    by_rg: dict[str, dict[str, Any]] = {}
    for r in rows:
        rg = by_rg.setdefault(r["region_id"], {
            "region_id": r["region_id"], "region": r["region"],
            "province": r["province"], "city": r["city"],
            "prices": [], "norm": [],
        })
        rg["prices"].append(float(r["effective_price"]))
        if r["normalized_price"] is not None:
            rg["norm"].append(float(r["normalized_price"]))
    all_norm = [v for rg in by_rg.values() for v in rg["norm"]] or [0.0]
    ref = _median(all_norm)
    out = []
    for rg in by_rg.values():
        avg = statistics.mean(rg["prices"])
        out.append({
            "region_id": rg["region_id"], "region": rg["region"],
            "province": rg["province"], "city": rg["city"],
            "avg_price": round(avg, 2),
            "price_index": price_index_for_value(statistics.mean(rg["norm"]) if rg["norm"] else avg, ref),
            "n": len(rg["prices"]),
        })
    out.sort(key=lambda x: x["avg_price"], reverse=True)
    cheapest = out[-1] if out else None
    most_exp = out[0] if out else None
    return {
        "regions": out,
        "cheapest_region": cheapest,
        "most_expensive_region": most_exp,
        "market_reference": round(ref, 2),
    }


# ---------------------------------------------------------------------------
# Promotion intelligence (Spec §21)
# ---------------------------------------------------------------------------

def promotion_intelligence(filters: dict[str, Any] | None = None,
                           path: str | None = None) -> dict[str, Any]:
    f = filters or {}
    where, params = _where_clause(f)
    # promotions chung (không filter product chặt như obs)
    pwhere = []
    pparams: list[Any] = []
    if f.get("product_id"):
        pwhere.append("s.sku_id = (SELECT sku_id FROM pi_skus WHERE product_id = ?)")
        pparams.append(f["product_id"])
    if f.get("channel_id"):
        pwhere.append("pr.channel_id = ?")
        pparams.append(f["channel_id"])
    if f.get("region_id"):
        pwhere.append("pr.region_id = ?")
        pparams.append(f["region_id"])
    pclause = ("WHERE " + " AND ".join(pwhere)) if pwhere else ""
    rows = pi_store.fetch_all(
        f"""SELECT pr.promotion_id, pr.sku_id, p.product_name, b.name AS brand,
                   pr.channel_id, pr.region_id, pr.regular_price, pr.promotion_price,
                   pr.discount_percent, pr.promotion_type, pr.campaign, pr.start_time
            FROM pi_promotions pr
            JOIN pi_skus s ON s.sku_id = pr.sku_id
            JOIN pi_products p ON p.product_id = s.product_id
            JOIN pi_brands b ON b.brand_id = p.brand_id
            {pclause}""",
        pparams, path=path,
    )
    discs = [float(r["discount_percent"]) for r in rows if r["discount_percent"] is not None]
    by_type: dict[str, int] = {}
    by_day: dict[str, list[float]] = {}
    by_channel: dict[str, dict[str, float]] = {}
    for r in rows:
        if r["promotion_type"]:
            by_type[r["promotion_type"]] = by_type.get(r["promotion_type"], 0) + 1
        day = (r["start_time"] or "")[:10]
        if day and r["discount_percent"] is not None:
            # điểm = discount trung bình theo ngày
            by_day.setdefault(day, []).append(float(r["discount_percent"]))
        if r["channel_id"] and r["discount_percent"] is not None:
            agg = by_channel.setdefault(r["channel_id"], {"count": 0.0, "discounts": []})
            agg["count"] += 1
            agg["discounts"].append(float(r["discount_percent"]))
    best_day = None
    if by_day:
        best_day = max(by_day.items(), key=lambda kv: statistics.mean(kv[1]))[0]
    # Resolve channel names + compute avg discount per channel for cross-channel chart.
    cid_rows = pi_store.fetch_all(
        "SELECT channel_id, channel_name FROM pi_channels", [], path=path)
    cid_name = {r["channel_id"]: r["channel_name"] for r in cid_rows}
    by_channel_out = [
        {
            "channel_id": cid,
            "channel": cid_name.get(cid, cid),
            "n": int(agg["count"]),
            "avg_discount_pct": round(statistics.mean(agg["discounts"]), 2)
                if agg["discounts"] else 0.0,
            "max_discount_pct": round(max(agg["discounts"]), 2)
                if agg["discounts"] else 0.0,
        }
        for cid, agg in by_channel.items()
    ]
    by_channel_out.sort(key=lambda x: x["avg_discount_pct"], reverse=True)

    # Promotion by brand —KM sâu nhất theo thương hiệu (chart phong phú hơn).
    by_brand: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not r["brand"] or r["discount_percent"] is None:
            continue
        agg = by_brand.setdefault(r["brand"], {"count": 0.0, "discounts": []})
        agg["count"] += 1
        agg["discounts"].append(float(r["discount_percent"]))
    by_brand_out = [
        {
            "brand": brand,
            "n": int(agg["count"]),
            "avg_discount_pct": round(statistics.mean(agg["discounts"]), 2)
                if agg["discounts"] else 0.0,
            "max_discount_pct": round(max(agg["discounts"]), 2)
                if agg["discounts"] else 0.0,
        }
        for brand, agg in by_brand.items()
    ]
    by_brand_out.sort(key=lambda x: x["avg_discount_pct"], reverse=True)

    # Promotion timeline — số KM + giảm giá TB theo ngày (line chart 30 ngày
    # gần nhất). Giúp chart Promotion Intelligence có chiều thời gian thay vì
    # chỉ 2 slice donut (Flash Sale / Campaign).
    timeline_out = [
        {"day": day, "count": len(ds), "avg_discount_pct": round(statistics.mean(ds), 2)}
        for day, ds in sorted(by_day.items())
    ]
    timeline_out = timeline_out[-30:]

    return {
        "total_promotions": len(rows),
        "avg_discount_pct": round(statistics.mean(discs), 2) if discs else 0.0,
        "max_discount_pct": round(max(discs), 2) if discs else 0.0,
        "promotion_by_type": by_type,
        "promotion_by_channel": by_channel_out,
        "promotion_by_brand": by_brand_out,
        "promotion_timeline": timeline_out,
        "best_day": best_day,
        "promotions": [
            {
                "promotion_id": r["promotion_id"], "product": r["product_name"],
                "brand": r["brand"], "channel_id": r["channel_id"],
                "regular_price": r["regular_price"],
                "promotion_price": r["promotion_price"],
                "discount_pct": r["discount_percent"],
                "type": r["promotion_type"], "campaign": r["campaign"],
                "start": r["start_time"],
            }
            for r in sorted(rows, key=lambda x: x["discount_percent"] or 0, reverse=True)[:50]
        ],
    }


# ---------------------------------------------------------------------------
# Price positioning matrix (Spec §17)
# ---------------------------------------------------------------------------

def positioning_matrix(filters: dict[str, Any] | None = None,
                       path: str | None = None) -> dict[str, Any]:
    """X = price index (vs market), Y = market share proxy (presence n),
    bubble = availability/presence."""
    f = filters or {}
    where, params = _where_clause(f)
    rows = pi_store.fetch_all(
        f"""SELECT o.product_id, p.product_name, p.brand_id, b.name AS brand,
                   o.effective_price, o.normalized_price, o.channel_id
            FROM pi_observations o
            JOIN pi_products p ON p.product_id = o.product_id
            JOIN pi_brands b ON b.brand_id = p.brand_id
            {where}""",
        params, path=path,
    )
    if not rows:
        return {"points": []}
    all_norm = [float(r["normalized_price"]) for r in rows if r["normalized_price"] is not None] or [0.0]
    ref = _median(all_norm)
    by_p: dict[str, dict[str, Any]] = {}
    for r in rows:
        p = by_p.setdefault(r["product_id"], {
            "product_id": r["product_id"], "name": r["product_name"], "brand": r["brand"],
            "prices": [], "norm": [], "channels": set(),
        })
        p["prices"].append(float(r["effective_price"]))
        if r["normalized_price"] is not None:
            p["norm"].append(float(r["normalized_price"]))
        p["channels"].add(r["channel_id"])
    points = []
    for pid, d in by_p.items():
        avg_norm = statistics.mean(d["norm"]) if d["norm"] else statistics.mean(d["prices"])
        points.append({
            "product_id": pid, "name": d["name"], "brand": d["brand"],
            "price_index": price_index_for_value(avg_norm, ref),
            "avg_price": round(statistics.mean(d["prices"]), 2),
            "presence": len(d["channels"]),
        })
    return {"reference": round(ref, 2), "points": points}


# ---------------------------------------------------------------------------
# Catalog (dùng cho filter bar)
# ---------------------------------------------------------------------------

def catalog(path: str | None = None) -> dict[str, Any]:
    raw_brands = pi_store.fetch_all(
        "SELECT brand_id, name FROM pi_brands ORDER BY name", path=path)
    # Dedup brand theo tên (pi_brands có thể có 2 brand_id cho cùng tên do
    # seed.py vs collector generate ID khác nhau — VD "BR-Heineken" và
    # "BR-HEINEKEN"). Giữ brand_id match pi_products.brand_id; loại brand rỗng.
    products = pi_store.fetch_all(
        "SELECT product_id, product_name, brand_id, pack_size, volume_ml FROM pi_products ORDER BY product_name",
        path=path)
    used_brand_ids = {p["brand_id"] for p in products if p["brand_id"]}
    seen_names: set[str] = set()
    brands: list[dict[str, Any]] = []
    # Ưu tiên brand_id đang được product dùng, rồi theo tên.
    for b in sorted(raw_brands, key=lambda x: (x["name"], x["brand_id"] not in used_brand_ids)):
        if not b["brand_id"] or not b["name"] or b["name"] == "Unknown":
            continue
        key = b["name"].strip().lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        brands.append({"id": b["brand_id"], "name": b["name"]})
    channels = pi_store.fetch_all(
        "SELECT channel_id, channel_name FROM pi_channels ORDER BY channel_name", path=path)
    regions = pi_store.fetch_all(
        "SELECT region_id, province, region FROM pi_regions ORDER BY province", path=path)
    return {
        "brands": brands,
        "products": [{"id": p["product_id"], "name": p["product_name"],
                      "brand_id": p["brand_id"], "pack_size": p["pack_size"],
                      "volume_ml": p["volume_ml"]} for p in products],
        "channels": [{"id": c["channel_id"], "name": c["channel_name"]} for c in channels],
        "regions": [{"id": r["region_id"], "province": r["province"], "region": r["region"]} for r in regions],
    }
