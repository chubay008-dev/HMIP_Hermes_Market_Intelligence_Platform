"""persistent_collector.py — Cào giá thật 1 LẦN duy nhất + cập nhật gia tăng.

Triết lý (theo yêu cầu):
- Cào dữ liệu thực tế 1 lần duy nhất, ghi vào DB. Đây là giá trị "gốc".
- Sau khi cào xong, dữ liệu thật được GIỮ CỐ ĐỊNH trên dashboard/workspace/pi
  (không re-seed lại từ đầu khi restart, không bị ghi đè).
- Các lần quét sau chỉ kiểm tra: nếu giá MỚI != giá hiện tại trong DB thì
  mới ghi observation mới (incremental). Tránh cào đi cào lại redundant.
- Mỗi lần phát hiện giá mới (thay đổi) → gửi alert qua Telegram + Discord.

Cơ chế marker: bảng pi_skus có cột metadata. Khi đã cào giá thật lần đầu,
đánh dấu metadata = '{"real_price_seeded": true}'. Lifespan kiểm tra marker
này → nếu có thì KHÔNG re-seed synthetic, giữ dữ liệu thật cố định.

Luồng:
  1. Startup: nếu DB rỗng (chưa có marker) → collect_realtime_persistent
     (cào 1 lần qua chain Firecrawl→ScraperAPI→ZenRows→Jina, ghi observation).
  2. Sau lần đầu → đánh dấu marker. Các lần restart sau giữ nguyên data.
  3. Scheduler chạy định kỳ → collect_incremental (chỉ ghi khi giá thay đổi).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from . import pi_store
from .collectors import PricePoint, _parse_pack_volume, ensure_catalog, store_price_point
from .normalization import normalize_price

log = logging.getLogger("hmip.persistent")

MARKER_KEY = "real_price_seeded"


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ---- marker -----------------------------------------------------------

def _get_sku_metadata(sku_id: str, path: str | None = None) -> dict[str, Any]:
    row = pi_store.fetch_one(
        "SELECT metadata FROM pi_skus WHERE sku_id = ?", [sku_id], path=path)
    if not row:
        return {}
    try:
        return json.loads(row["metadata"]) if row["metadata"] else {}
    except (ValueError, TypeError):
        return {}


def _set_sku_metadata(sku_id: str, meta: dict[str, Any], path: str | None = None) -> None:
    with pi_store._session(path or pi_store.DEFAULT_PI_DB_PATH) as c:  # type: ignore[attr-defined]
        c.execute(
            "UPDATE pi_skus SET metadata = ? WHERE sku_id = ?",
            (json.dumps(meta, ensure_ascii=False), sku_id),
        )


def has_real_prices(path: str | None = None) -> bool:
    """True nếu đã cào giá thật ít least 1 SKU (marker đặt).

    Dùng để quyết định: có re-seed synthetic không? Có marker → KHÔNG seed.
    """
    try:
        rows = pi_store.fetch_all(
            "SELECT metadata FROM pi_skus WHERE metadata IS NOT NULL AND metadata != ''",
            [], path=path)
        for r in rows:
            try:
                if json.loads(r["metadata"]).get(MARKER_KEY):
                    return True
            except (ValueError, TypeError):
                continue
    except Exception:
        pass
    return False


def _mark_real_seeded(sku_id: str, path: str | None = None) -> None:
    meta = _get_sku_metadata(sku_id, path=path)
    meta[MARKER_KEY] = True
    _set_sku_metadata(sku_id, meta, path=path)


# ---- latest price lookup ---------------------------------------------

def _latest_observation(pp: PricePoint, path: str | None = None) -> dict[str, Any] | None:
    """Observation gần nhất cho (sku, channel, region) — để so sánh giá.

    ORDER BY observation_id DESC: observation_id có timestamp suffix
    (int(time.time()) % 100000) → đảm bảo lấy row MỚI NHẤT deterministic,
    tránh ghi trùng khi trigger chạy nhiều lần trong cùng ngày.
    """
    return pi_store.fetch_one(
        """SELECT o.effective_price, o.regular_price, o.unit_price,
                  s.pack_quantity, o.observed_at
           FROM pi_observations o
           LEFT JOIN pi_skus s ON s.sku_id = o.sku_id
           WHERE o.sku_id = ? AND o.channel_id = ? AND o.region_id = ?
           ORDER BY o.observed_at DESC, o.observation_id DESC LIMIT 1""",
        [pp.sku_id, pp.channel_id, pp.region_id], path=path)


# ---- incremental store + notify --------------------------------------

def _resolve_brand_id(product_id: str, path: str | None = None) -> str:
    """Lấy brand_id chuẩn từ pi_products (không dùng brand_id trống).

    Observation ghi brand_id rỗng → JOIN pi_brands match ('', 'Unknown') →
    Competitor Comparison / Price Index hiển thị "Unknown". Resolve từ product
    để observation kế thừa brand chuẩn."""
    row = pi_store.fetch_one(
        "SELECT brand_id FROM pi_products WHERE product_id = ?",
        [product_id], path=path)
    return (row["brand_id"] if row and row["brand_id"] else "")


def store_price_point_if_changed(
    pp: PricePoint, today: str | None = None, path: str | None = None,
    notify: bool = True, threshold_pct: float = 1.0,
) -> dict[str, Any]:
    """Lưu PricePoint CHỈ khi giá hiệu lực thay đổi so với observation cuối.

    Trả: {"inserted": bool, "old_price": float|None, "new_price": float,
          "changed": bool, "notified": dict}
    - inserted=False khi giá mới == giá cũ (trong threshold) → không cào lại redundant.
    - inserted=True khi giá mới khác → ghi observation mới + (tuỳ chọn) notify.

    threshold_pct: % sai số nhỏ nhất để coi là "thay đổi" (mặc định 1% →
    bỏ qua noise +-1% do làm tròn/định dạng).
    """
    ensure_catalog(path=path)
    latest = _latest_observation(pp, path=path)
    norm = normalize_price(
        regular_price=pp.regular_price,
        promotion_price=pp.promotion_price,
        pack_quantity=pp.pack_quantity,
        unit_volume_ml=pp.unit_volume_ml,
    )
    # Giá hiệu lực & giá/LON (per-unit). So sánh/alert dùng giá/LON để
    # apples-to-apples giữa các observation có pack khác nhau (thùng 24 vs lon lẻ).
    # Trước đây so sánh raw effective_price → pack-mismatch sinh alert sai
    # (vd box 1.15M vs lon 15k → "-98.67%" giả tạo). Giờ so trên per-lon.
    new_eff = float(norm.effective_price)
    new_lon = float(norm.price_per_unit)

    result: dict[str, Any] = {
        "inserted": False, "old_price": None, "new_price": round(new_lon, 2),
        "changed": False, "notified": {"discord": False, "telegram": False},
    }

    if latest:
        # Ưu tiên unit_price (giá/LON đã chuẩn hoá lúc insert). Nếu DB cũ chưa
        # có unit_price (pre-fix) → suy lại từ effective_price / pack_quantity.
        old_lon = latest.get("unit_price")
        if old_lon is None or float(old_lon or 0) <= 0:
            old_eff = float(latest["effective_price"])
            old_pack = float(latest.get("pack_quantity") or pp.pack_quantity or 1) or 1
            old_lon = old_eff / old_pack
        old_lon = float(old_lon)
        result["old_price"] = round(old_lon, 2)
        if old_lon > 0:
            change_pct = abs(new_lon - old_lon) / old_lon * 100.0
            if change_pct < threshold_pct:
                # Giá/LON không đổi (trong noise threshold) → không ghi, không notify.
                return result
        result["changed"] = True

    # Giá mới (hoặc chưa có observation nào) → ghi observation mới.
    ts = today or time.strftime("%Y-%m-%d")
    obs_id = f"OBS-{pp.source}-{pp.sku_id}-{ts}-{int(time.time()) % 100000}"
    # Resolve brand_id chuẩn từ product (không hardcode "" → tránh "Unknown"
    # trong Competitor Comparison / Price Index khi JOIN pi_brands).
    brand_id = _resolve_brand_id(pp.product_id, path=path)
    pi_store.insert_observation(
        observation_id=obs_id,
        sku_id=pp.sku_id, product_id=pp.product_id, brand_id=brand_id,
        channel_id=pp.channel_id, seller_id="UNKNOWN", region_id=pp.region_id,
        observed_at=ts, collected_at=ts,
        regular_price=pp.regular_price, effective_price=new_eff,
        currency="VND", promotion_price=pp.promotion_price,
        unit_price=new_lon, normalized_price=norm.price_per_100ml,
        availability="in_stock", source=pp.source, source_url=None,
        extraction_method=pp.source, confidence=0.9, metadata=None, path=path,
    )
    result["inserted"] = True

    # Đánh dấu SKU đã có giá thật (marker one-time seed).
    _mark_real_seeded(pp.sku_id, path=path)

    # Notify khi có sự thay đổi giá/LON (không phải lần đầu ghi).
    if notify and result["changed"] and result["old_price"]:
        try:
            from . import notifier
            from .models import DEFAULT_THRESHOLDS, Severity
            # Resolve tên SP thật từ catalog để cross-hệ cooldown key khớp
            # (trước đây ghi product_id "P123" → key khác scheduler scan truyền
            # tên thật "Bia Huda" → cross-hệ skip không hoạt động → spam).
            try:
                from extensions.default_products import DEFAULT_PRODUCTS
                pname = DEFAULT_PRODUCTS.get(pp.product_id, {}).get(
                    "product_name", pp.product_id)
            except Exception:
                pname = pp.product_id
            old = result["old_price"]
            new = result["new_price"]
            change = (new - old) / old * 100.0 if old else 0.0
            change_abs = abs(change)
            # Severity theo magnitude thực (không cứng CRITICAL) để message
            # phản ánh đúng mức độ; filter min-change/cooldown ở notify_alert.
            if change_abs >= DEFAULT_THRESHOLDS["high"]:
                sev = Severity.CRITICAL
            elif change_abs >= DEFAULT_THRESHOLDS["medium"]:
                sev = Severity.HIGH
            elif change_abs >= DEFAULT_THRESHOLDS["low"]:
                sev = Severity.MEDIUM
            else:
                sev = Severity.LOW
            alert = {
                "event_type": "PRICE_INCREASE" if change > 0 else "PRICE_DECREASE",
                "sku_id": pp.sku_id, "product_name": pname,
                "channel_id": pp.channel_id, "region_id": pp.region_id,
                # Giá/LON (đã chuẩn hoá) — luôn cùng đơn vị, so sánh đúng.
                "old_price": round(old, 2), "new_price": round(new, 2),
                "change_pct": round(change, 2), "severity": sev.value,
                "timestamp": _now_iso(),
                "source": pp.source,
                "pack_size": pp.pack_quantity or 24,
                "unit_ml": pp.unit_volume_ml or 330,
            }
            result["notified"] = notifier.notify_alert(alert)
        except Exception as exc:
            log.warning("Notify failed: %s", exc)

    return result


# ---- chain orchestration ---------------------------------------------

def _collect_via_chain(limit: int | None, path: str | None,
                       incremental: bool) -> dict[str, Any]:
    """Chạy chain collector theo thứ tự 1-4, dừng tại tier đầu tiên thành công.

    Thứ tự (theo yêu cầu):
      1. Firecrawl   (đáng tin nhất, có credit)
      2. ScraperAPI  (render JS, free 5000/tháng)
      3. ZenRows     (render JS, free 1000/tháng)
      4. Jina        (free, không render JS — thường None cho Tiki SPA)

    Mỗi tier chạy toàn bộ catalog. Nếu tier có collected > 0 → trả luôn,
    không chạy tier sau (tiết kiệm credit, tránh cào lại).

    incremental=True: dùng store_price_point_if_changed (chỉ ghi khi đổi).
    incremental=False: dùng store_price_point (ghi tất cả, cho lần seed đầu).
    """
    from extensions.default_products import DEFAULT_PRODUCTS
    from .channels import configured_channels
    ensure_catalog(path=path)

    tiers: list[tuple[str, Any]] = []
    # Tier 1: Firecrawl
    try:
        from . import firecrawl_collector as fc
        if (fc.FirecrawlCollector().api_key or "").strip():
            tiers.append(("firecrawl", fc.FirecrawlCollector()))
    except Exception as exc:
        log.warning("Firecrawl tier skip: %s", exc)
    # Tier 2: ScraperAPI
    try:
        from . import scraperapi_collector as sa
        if (sa.ScraperAPICollector().api_key or "").strip():
            tiers.append(("scraperapi", sa.ScraperAPICollector()))
    except Exception as exc:
        log.warning("ScraperAPI tier skip: %s", exc)
    # Tier 3: ZenRows
    try:
        from . import zenrows_collector as zr
        if (zr.ZenRowsCollector().api_key or "").strip():
            tiers.append(("zenrows", zr.ZenRowsCollector()))
    except Exception as exc:
        log.warning("ZenRows tier skip: %s", exc)
    # Tier 4: Jina (luôn khả dụng, không cần key)
    try:
        from . import jina_collector as jc
        tiers.append(("jina", jc.JinaCollector()))
    except Exception as exc:
        log.warning("Jina tier skip: %s", exc)

    if not tiers:
        return {"source_used": "none", "collected": 0, "failed": 0, "total": 0,
                "error": "no collector configured"}

    _all = list(DEFAULT_PRODUCTS.items())
    _prio = os.getenv("HMIP_PI_PRODUCTS", "").strip()
    if _prio:
        _pids = {p.strip() for p in _prio.split(",") if p.strip()}
        _all = [(pid, m) for pid, m in _all if pid in _pids]
    items = _all[:limit] if limit else _all
    total = len(items)
    # Multi-channel: quét từng kênh configured (env HMIP_CHANNELS, default TIKI).
    # Mỗi kênh = observation riêng (channel_id khác) → so sánh cross-channel.
    chan_list = configured_channels()

    for tier_name, collector in tiers:
        collected = changed = skipped = failed = 0
        for chan in chan_list:
            for pid, meta in items:
                name = str(meta["product_name"])
                try:
                    pp = collector.collect(pid, name, channel=chan)
                except Exception as exc:
                    log.warning("%s[%s] collect %s err: %s", tier_name,
                                chan.channel_id, pid, exc)
                    pp = None
                if pp:
                    if incremental:
                        res = store_price_point_if_changed(pp, path=path, notify=True)
                        if res["inserted"]:
                            collected += 1
                            if res["changed"]:
                                changed += 1
                        else:
                            # Giá không đổi (trong noise threshold) → skip, KHÔNG phải fail.
                            skipped += 1
                    else:
                        store_price_point(pp, path=path)
                        collected += 1
                        _mark_real_seeded(pp.sku_id, path=path)
                else:
                    failed += 1
                time.sleep(0.6)
        # Tier thành công nếu: có observation mới (collected>0) HOẶC có giá
        # không đổi (skipped>0, tức tier lấy được giá nhưng không cần ghi lại).
        # Chỉ xuống tier sau khi cả collected và skipped đều 0 (không lấy được giá).
        # Multi-channel: thành công nếu TỔNG qua các kênh > 0 (không yêu cầu
        # tất cả kênh đều có giá — Shopee/Lazada có thể fail do bot protection).
        if collected > 0 or skipped > 0:
            return {"source_used": tier_name, "collected": collected,
                    "changed": changed, "skipped": skipped, "failed": failed,
                    "total": total}
        log.info("Tier %s thu 0 sản phẩm → thử tier tiếp theo", tier_name)

    last = tiers[-1][0]
    return {"source_used": last, "collected": 0, "changed": 0, "skipped": 0,
            "failed": total, "total": total, "error": "all tiers failed"}


def collect_realtime_persistent(limit: int | None = None,
                                path: str | None = None) -> dict[str, Any]:
    """Cào giá thật LẦN ĐẦU (one-time seed): ghi toàn bộ, không incremental.

    Dùng khi DB chưa có giá thật (marker chưa đặt). Sau khi xong, marker
    được đặt → các lần restart sau KHÔNG re-seed, giữ dữ liệu cố định.
    """
    ensure_catalog(path=path)
    return _collect_via_chain(limit, path, incremental=False)


def collect_incremental(limit: int | None = None,
                        path: str | None = None) -> dict[str, Any]:
    """Quét định kỳ: chỉ ghi observation khi giá thay đổi + notify.

    Dùng sau lần seed đầu. Trả summary bao gồm số giá mới phát hiện.
    """
    return _collect_via_chain(limit, path, incremental=True)


def collect_smart(limit: int | None = None,
                  path: str | None = None) -> dict[str, Any]:
    """Entry point thống nhất: seed lần đầu HOẶC incremental.

    - Nếu chưa có giá thật (marker) → collect_realtime_persistent (lần đầu).
    - Nếu đã có → collect_incremental (chỉ cập nhật khi đổi).
    """
    ensure_catalog(path=path)
    if has_real_prices(path=path):
        log.info("Đã có giá thật → chạy incremental scan (chỉ ghi khi đổi)")
        return collect_incremental(limit, path)
    log.info("Chưa có giá thật → cào lần đầu (one-time seed)")
    return collect_realtime_persistent(limit, path)
