"""collectors.py — Thu thập giá THẬT từ các sàn TMĐT (Hướng A+C).

Thiết kế:
- Tiki: scrape API công khai /api/v2/products (JSON, ít chặn) — HOẠT ĐỘNG.
- Shopee/Lazada: stub (cần cookie/proxy/partner-key) — Hướng C, ghi rõ cách
  hoàn thiện sau. Không scrape liều (bị block ngay).
- Mọi collector chuẩn hóa về PricePoint qua normalization.normalize_price
  (Pack -> Unit -> 100ml) để đồng nhất với data demo.

Chỉ mở rộng extensions/pi, không sửa core/domains.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from . import pi_store
from .normalization import normalize_price

log = logging.getLogger("hmip.collectors")

TIKI_SEARCH = "https://tiki.vn/api/v2/products"
TIKI_HOME = "https://tiki.vn/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "vi-VN,vi;q=0.9",
}
_REQUEST_TIMEOUT = 20
# Tiki chặn nếu gọi quá nhanh; nghỉ giữa các sản phẩm.
_REQ_GAP_S = 0.6


def _get_guest_token() -> str | None:
    """Tiki API cần x-guest-token (lấy từ cookie trang chủ)."""
    try:
        r = requests.get(TIKI_HOME, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        # token nằm trong cookie 'tiki_token' hoặc JS window.__TOKEN
        tok = r.cookies.get("tiki_token")
        if not tok:
            import re
            m = re.search(r"window\.__TOKEN\s*=\s*[\"']([^\"']+)[\"']", r.text)
            tok = m.group(1) if m else None
        return tok
    except Exception:
        return None


@dataclass
class PricePoint:
    product_id: str
    sku_id: str
    channel_id: str
    region_id: str
    regular_price: float
    promotion_price: float | None
    pack_quantity: int
    unit_volume_ml: int
    source: str
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_pack_volume(name: str) -> tuple[int, int]:
    """Trích pack_quantity + unit_volume_ml từ tên Tiki.

    Vd: 'Thùng 24 lon bia Heineken (330ml / Lon)' -> (24, 330)
        'Bia Tiger 330ml' -> (1, 330)
    """
    vol = 330
    m = re.search(r"(\d+)\s*ml", name, re.I)
    if m:
        vol = int(m.group(1))
    pack = 1
    m = re.search(r"(\d+)\s*lon|thùng\s*(\d+)|chai\s*(\d+)", name, re.I)
    if m:
        pack = int(next(g for g in m.groups() if g))
    # Heuristic: 'Thùng' thường 6/12/24
    if "thùng" in name.lower() and pack == 1:
        pack = 24
    return pack, vol


def _match_best(items: list[dict[str, Any]], want_name: str, vol: int) -> dict[str, Any] | None:
    """Chọn item khớp nhất: chứa volume + gần tên nhất."""
    want = want_name.lower()
    vol_s = f"{vol}ml"
    scored = []
    for it in items:
        n = (it.get("name") or "").lower()
        if vol_s not in n:
            continue
        score = 1 if want.split()[0] in n else 0
        scored.append((score, it))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
    return items[0] if items else None


class TikiCollector:
    """Collector Tiki (API công khai, best-effort)."""

    source = "tiki"

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        last_err = None
        token = _get_guest_token()
        headers = dict(_HEADERS)
        if token:
            headers["x-guest-token"] = token
        for attempt in range(3):
            try:
                r = requests.get(
                    TIKI_SEARCH,
                    params={"q": query, "limit": limit},
                    headers=headers,
                    timeout=_REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    last_err = f"HTTP {r.status_code}"
                    time.sleep(1.0 * (attempt + 1))
                    continue
                try:
                    data = r.json()
                except ValueError:
                    last_err = "non-json response"
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return data.get("data", []) or []
            except Exception as exc:
                last_err = str(exc)
                time.sleep(1.0 * (attempt + 1))
        log.warning("Tiki search failed after retries %r: %s", query, last_err)
        return []

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        pack, vol = _parse_pack_volume(product_name)
        items = self.search(product_name, limit=10)
        best = _match_best(items, product_name, vol or ref_vol)
        if not best:
            return None
        price = best.get("price") or best.get("list_price")
        if not price:
            return None
        promo = best.get("list_price")
        promo_price = promo if (promo and promo > price) else None
        return PricePoint(
            product_id=product_id,
            sku_id=f"SKU-{product_id}",
            channel_id="TIKI",
            region_id="ONLINE",
            regular_price=float(price),
            promotion_price=float(promo_price) if promo_price else None,
            pack_quantity=pack,
            unit_volume_ml=vol or ref_vol,
            source=self.source,
            raw=best,
        )


class ShopeeCollector:
    """Stub — Shopee chặn scrape công khai (cần cookie/csrf động + proxy).

    Hoàn thiện sau: dùng Shopee Partner/Affiliate API (cần đăng ký seller
    app -> app-key/secret) hoặc headless browser xoay cookie. Không scrape
    liều từ server đơn vì sẽ bị block IP.
    """

    source = "shopee"

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330):
        raise NotImplementedError(
            "Shopee cần Partner API key hoặc cookie động + proxy. "
            "Xem Hướng dẫn: đăng ký Shopee Open Platform, đặt env "
            "SHOPEE_API_KEY, rồi implement collect() qua /api/v4/search."
        )


class LazadaCollector:
    """Stub — Lazada có bot protection (Akamai), cần Open Platform key."""

    source = "lazada"

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330):
        raise NotImplementedError(
            "Lazada cần Lazada Open Platform app key/secret. "
            "Đăng ký developer app, đặt env LAZADA_API_KEY, implement qua "
            "Lazada API /products/search."
        )


COLLECTORS = {
    "TIKI": TikiCollector,
    "SHOPEE": ShopeeCollector,
    "LAZADA": LazadaCollector,
}


def collect_product(channel: str, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
    cls = COLLECTORS.get(channel.upper())
    if not cls:
        return None
    try:
        return cls().collect(product_id, product_name, ref_vol)
    except NotImplementedError:
        raise
    except Exception as exc:
        log.warning("%s collect failed for %s: %s", channel, product_id, exc)
        return None


_CATALOG_READY: set[str] = set()  # per-path cache: ensure_catalog chạy 1 lần/path


def ensure_catalog(path: str | None = None) -> None:
    """Tạo bảng + bảng cha (category/channel/region/product/sku) nếu chưa có.

    Idempotent — KHÔNG xóa data. Dùng trước khi lưu observation từ collector.
    Cache per-path: chỉ chạy 1 lần/path (catalog immutable) để tránh
    ~90 round-trip lên PostgreSQL (Supabase pooler) mỗi lần collect.
    Batch: toàn bộ catalog upsert trong 1 connection (1 commit cuối).
    """
    from . import pi_store as _ps_for_default
    cache_key = path or _ps_for_default.DEFAULT_PI_DB_PATH
    if cache_key in _CATALOG_READY:
        return
    from extensions.default_products import DEFAULT_PRODUCTS
    from . import pi_store as ps

    ps.init_pi_db(path)  # tạo schema nếu chưa có (1 round-trip)
    # Batch: 1 connection cho toàn bộ catalog upsert (tránh 90 round-trip).
    with ps._session(path or ps.DEFAULT_PI_DB_PATH) as c:  # type: ignore[attr-defined]
        # Dimension rows (category/seller/brand/channels/regions).
        c.execute(
            "INSERT INTO pi_categories (category_id, name) VALUES (?, ?) "
            "ON CONFLICT(category_id) DO UPDATE SET name=excluded.name",
            ("BEER", "Beer & Beverage"))
        c.execute(
            "INSERT INTO pi_sellers (seller_id, seller_name, seller_type) VALUES (?, ?, ?) "
            "ON CONFLICT(seller_id) DO UPDATE SET seller_name=excluded.seller_name, "
            "seller_type=excluded.seller_type",
            ("UNKNOWN", "Unknown", "unknown"))
        c.execute(
            "INSERT INTO pi_brands (brand_id, name) VALUES (?, ?) "
            "ON CONFLICT(brand_id) DO UPDATE SET name=excluded.name",
            ("", "Unknown"))
        for cid, cname, ctype in [
            ("SHOPEE", "Shopee", "ecommerce"),
            ("LAZADA", "Lazada", "ecommerce"),
            ("TIKI", "Tiki", "ecommerce"),
            ("AEON", "AEON", "retail"),
            ("WINMART", "WinMart", "retail"),
        ]:
            c.execute(
                "INSERT INTO pi_channels (channel_id, channel_name, channel_type) "
                "VALUES (?, ?, ?) ON CONFLICT(channel_id) DO UPDATE SET "
                "channel_name=excluded.channel_name, channel_type=excluded.channel_type",
                (cid, cname, ctype))
        for rid, country, region, province in [
            ("HANOI", "VN", "North", "Hà Nội"),
            ("HCM", "VN", "South", "TP.HCM"),
            ("DANANG", "VN", "Central", "Đà Nẵng"),
            ("HAIPHONG", "VN", "North", "Hải Phòng"),
            ("CANTHO", "VN", "Mekong", "Cần Thơ"),
            ("ONLINE", "VN", "Online", "Online"),
        ]:
            c.execute(
                "INSERT INTO pi_regions (region_id, country, region, province, city) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(region_id) DO UPDATE SET "
                "country=excluded.country, region=excluded.region, "
                "province=excluded.province, city=excluded.city",
                (rid, country, region, province, province))
        for pid, meta in DEFAULT_PRODUCTS.items():
            brand = str(meta["brand"])
            bid = f"BR-{brand.upper().replace(' ', '')}"
            c.execute(
                "INSERT INTO pi_brands (brand_id, name) VALUES (?, ?) "
                "ON CONFLICT(brand_id) DO UPDATE SET name=excluded.name",
                (bid, brand))
            c.execute(
                "INSERT INTO pi_products (product_id, brand_id, category_id, product_name, "
                "variant, pack_size, volume_ml, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(product_id) DO UPDATE SET brand_id=excluded.brand_id, "
                "category_id=excluded.category_id, product_name=excluded.product_name, "
                "variant=excluded.variant, pack_size=excluded.pack_size, "
                "volume_ml=excluded.volume_ml, unit=excluded.unit",
                (pid, bid, "BEER", str(meta["product_name"]), None, None,
                 float(meta.get("volume_ml", 330)), "ml"))
            variant_name = str(meta.get("variant", "Original"))
            vid = f"VAR-{pid}"
            c.execute(
                "INSERT INTO pi_variants (variant_id, product_id, name, slug, attributes) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(variant_id) DO UPDATE SET "
                "product_id=excluded.product_id, name=excluded.name, "
                "slug=excluded.slug, attributes=excluded.attributes",
                (vid, pid, variant_name, variant_name.lower().replace(" ", "-"), None))
            c.execute(
                "INSERT INTO pi_skus (sku_id, product_id, barcode, pack_quantity, "
                "unit_volume_ml, normalized_unit) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(sku_id) DO UPDATE SET product_id=excluded.product_id, "
                "barcode=excluded.barcode, pack_quantity=excluded.pack_quantity, "
                "unit_volume_ml=excluded.unit_volume_ml, "
                "normalized_unit=excluded.normalized_unit",
                (f"SKU-{pid}", pid, None, float(meta.get("pack_quantity", 1)),
                 float(meta.get("volume_ml", 330)), "100ml"))
            c.execute(
                "INSERT INTO pi_source_listings "
                "(listing_id, sku_id, channel_id, seller_id, region_id, source_url, "
                "external_id) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(listing_id) DO UPDATE SET sku_id=excluded.sku_id, "
                "channel_id=excluded.channel_id, seller_id=excluded.seller_id, "
                "region_id=excluded.region_id, source_url=excluded.source_url, "
                "external_id=excluded.external_id",
                (f"LST-TIKI-{pid}", f"SKU-{pid}", "TIKI", "UNKNOWN", "ONLINE", None, None))
    _CATALOG_READY.add(cache_key)  # cache: skip các lần gọi sau (catalog immutable)


def store_price_point(pp: PricePoint, today: str | None = None, path: str | None = None) -> None:
    """Chuẩn hóa + lưu 1 PricePoint vào PI DB (thay seed)."""
    ensure_catalog(path=path)  # đảm bảo bảng cha tồn tại (idempotent, không xóa)
    norm = normalize_price(
        regular_price=pp.regular_price,
        promotion_price=pp.promotion_price,
        pack_quantity=pp.pack_quantity,
        unit_volume_ml=pp.unit_volume_ml,
    )
    eff = pp.promotion_price if pp.promotion_price else pp.regular_price
    ts = today or time.strftime("%Y-%m-%d")
    pi_store.insert_observation(
        observation_id=f"OBS-{pp.source}-{pp.sku_id}-{ts}",
        sku_id=pp.sku_id,
        product_id=pp.product_id,
        brand_id="",
        channel_id=pp.channel_id,
        seller_id="UNKNOWN",
        region_id=pp.region_id,
        observed_at=ts,
        collected_at=ts,
        regular_price=pp.regular_price,
        effective_price=eff,
        currency="VND",
        promotion_price=pp.promotion_price,
        unit_price=norm.price_per_unit,
        normalized_price=norm.price_per_100ml,
        availability="in_stock",
        source=pp.source,
        source_url=None,
        extraction_method="api",
        confidence=0.8,
        metadata=None,
        path=path,
    )


def collect_realtime(channel: str = "TIKI", limit: int | None = None, path: str | None = None) -> dict[str, Any]:
    """Quét giá thật cho catalog, lưu vào PI DB.

    Trả summary: {collected, failed, total}. Chỉ Tiki hoạt động; Shopee/Lazada
    sẽ raise NotImplementedError (bắt ở caller).
    """
    from extensions.default_products import DEFAULT_PRODUCTS

    # Đảm bảo bảng cha (products/skus/channels/regions) tồn tại để FK hợp lệ.
    ensure_catalog(path=path)

    collected = 0
    failed = 0
    total = 0
    for pid, meta in list(DEFAULT_PRODUCTS.items())[:limit]:
        total += 1
        name = str(meta["product_name"])
        try:
            pp = collect_product(channel, pid, name)
        except NotImplementedError as exc:
            raise
        if pp:
            store_price_point(pp)
            collected += 1
        else:
            failed += 1
        time.sleep(_REQ_GAP_S)
    return {"channel": channel, "collected": collected, "failed": failed, "total": total}


def collect_realtime_smart(limit: int | None = None, path: str | None = None) -> dict[str, Any]:
    """Quét giá thật thông minh: seed lần đầu + cập nhật gia tăng.

    Delegate sang persistent_collector.collect_smart để duy trì hành vi:
    - Lần đầu (chưa có giá thật): cào 1 lần qua chain Firecrawl→ScraperAPI→
      ZenRows→Jina, ghi toàn bộ observation, đánh dấu marker.
    - Các lần sau: chỉ ghi observation khi giá thay đổi + notify Telegram/Discord.

    Thứ tự tier (theo yêu cầu): 1-Firecrawl, 2-ScraperAPI, 3-ZenRows, 4-Jina.
    Dừng tại tier đầu tiên thành công (collected > 0) để tiết kiệm credit.

    Vẫn giữ fallback 4-tier cũ (Tiki API→Firecrawl→Jina→Crawl4AI) nếu
    persistent_collector không khả dụng (import lỗi).
    """
    try:
        from . import persistent_collector as pc
        return pc.collect_smart(limit=limit, path=path)
    except Exception as exc:
        log.warning("persistent_collector fail, fallback legacy chain: %s", exc)

    # Legacy fallback (để đảm bảo không break nếu marker logic lỗi)
    # Tier 1: Tiki API (free, không tốn tiền)
    tk = collect_realtime(channel="TIKI", limit=limit, path=path)
    if tk.get("collected", 0) > 0:
        tk["source_used"] = "tiki-api"
        return tk

    # Tier 2: Firecrawl (nếu có key + chưa hết credit)
    from . import firecrawl_collector as fc
    if (fc.FirecrawlCollector().api_key or "").strip():
        fc_res = fc.collect_realtime_firecrawl(channel="TIKI", limit=limit, path=path)
        if fc_res.get("collected", 0) > 0:
            fc_res["source_used"] = "firecrawl"
            return fc_res
        log.warning("Firecrawl fail (có thể hết credit) -> tier 3 Jina")

    # Tier 3: Jina Reader (free)
    from . import jina_collector as jc
    jr = jc.collect_realtime_jina(channel="TIKI", limit=limit, path=path)
    if jr.get("collected", 0) > 0:
        jr["source_used"] = "jina-reader"
        return jr

    # Tier 4: Crawl4AI (self-host, free, cần chromium) — chỉ nếu bật env
    if os.getenv("CRAWL4AI_ENABLED", "false").lower() in ("1", "on", "true", "yes"):
        try:
            from . import crawl4ai_collector as ca
            ca_res = ca.collect_realtime_crawl4ai(channel="TIKI", limit=limit, path=path)
            if ca_res.get("collected", 0) > 0:
                ca_res["source_used"] = "crawl4ai"
                return ca_res
        except Exception as exc:
            log.warning("Crawl4AI tier fail: %s", exc)

    # Tất cả fail: trả tier3 (dù có thể 0) để caller biết
    jr["source_used"] = "jina-reader"
    return jr


