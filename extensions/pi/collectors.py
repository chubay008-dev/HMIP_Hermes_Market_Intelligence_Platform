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
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from . import pi_store
from .normalization import normalize_price

log = logging.getLogger("hmip.collectors")

TIKI_SEARCH = "https://tiki.vn/api/v2/products"
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
        for attempt in range(3):
            try:
                r = requests.get(
                    TIKI_SEARCH,
                    params={"q": query, "limit": limit},
                    headers=_HEADERS,
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


def ensure_catalog(path: str | None = None) -> None:
    """Tạo bảng + bảng cha (category/channel/region/product/sku) nếu chưa có.

    Idempotent — KHÔNG xóa data. Dùng trước khi lưu observation từ collector.
    """
    from extensions.default_products import DEFAULT_PRODUCTS
    from . import pi_store as ps

    ps.init_pi_db(path)  # tạo schema nếu chưa có
    ps.upsert_category("BEER", "Beer & Beverage", path=path)
    # Seller + Brand mặc định (observations cần FK hợp lệ).
    ps.upsert_seller("UNKNOWN", "Unknown", "unknown", path=path)
    ps.upsert_brand("", "Unknown", path=path)
    for cid, cname, ctype in [
        ("SHOPEE", "Shopee", "ecommerce"),
        ("LAZADA", "Lazada", "ecommerce"),
        ("TIKI", "Tiki", "ecommerce"),
        ("AEON", "AEON", "retail"),
        ("WINMART", "WinMart", "retail"),
    ]:
        ps.upsert_channel(cid, cname, ctype, path=path)
    for rid, country, region, province in [
        ("HANOI", "VN", "North", "Hà Nội"),
        ("HCM", "VN", "South", "TP.HCM"),
        ("DANANG", "VN", "Central", "Đà Nẵng"),
        ("HAIPHONG", "VN", "North", "Hải Phòng"),
        ("CANTHO", "VN", "Mekong", "Cần Thơ"),
        ("ONLINE", "VN", "Online", "Online"),
    ]:
        ps.upsert_region(rid, country, region, province, city=province, path=path)
    for pid, meta in DEFAULT_PRODUCTS.items():
        brand = str(meta["brand"])
        bid = f"BR-{brand.upper().replace(' ', '')}"
        ps.upsert_brand(bid, brand, path=path)
        ps.upsert_product(pid, bid, "BEER", str(meta["product_name"]),
                         variant=None, pack_size=None, volume_ml=float(meta.get("volume_ml", 330)),
                         unit="ml", path=path)
        ps.upsert_sku(f"SKU-{pid}", pid, barcode=None,
                      pack_quantity=float(meta.get("pack_quantity", 1)),
                      unit_volume_ml=float(meta.get("volume_ml", 330)),
                      normalized_unit="100ml", path=path)


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
