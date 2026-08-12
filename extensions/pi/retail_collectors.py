"""retail_collectors.py — Collector các nguồn web bán lẻ VN (Hướng thêm nguồn).

Mục tiêu của user: quét "toàn bộ các nguồn web uy tín" — WinMart, BachHoaXanh,
Websosanh, Aeon, Emart, CoopMart, Facebook,...

Thiết kế:
- BaseRetailCollector: template crawl HTML + regex trích giá (best-effort).
  Mỗi nguồn override SEARCH_URL + parse(). Do các site SPA/JS-heavy, parser
  là heuristic — user tinh chỉnh selector khi deploy thật.
- Facebook/Zalo/TikTok Shop: KHÔNG có API giá công khai, bot-protection mạnh
  -> để stub (NotImplementedError) giống Shopee/Lazada. Khuyến nghị không
  scrape nguồn mạng xã hội làm giá chuẩn.
- Mọi kết quả chuẩn hóa qua normalization (Pack->Unit->100ml) rồi lưu qua
  collectors.store_price_point.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import quote as _urlquote

import requests

from .collectors import PricePoint, _REQ_GAP_S, _HEADERS, store_price_point

log = logging.getLogger("hmip.retail_collectors")

_PRICE_RE = re.compile(r"([\d][\d\.,]{2,})\s*(?:đ|VND|vnđ)", re.I)


class BaseRetailCollector:
    source = "retail"
    search_url = ""  # override: "{q}" được format vào query
    base_channel = "RETAIL"

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not self.search_url:
            return []
        try:
            r = requests.get(self.search_url.format(q=_urlquote(query)),
                             headers=_HEADERS, timeout=20)
            if r.status_code != 200:
                log.warning("%s HTTP %s", self.source, r.status_code)
                return []
            return self.parse(r.text, query)
        except Exception as exc:
            log.warning("%s error: %s", self.source, exc)
            return []

    def parse(self, html: str, query: str) -> list[dict[str, Any]]:
        """Heuristic: tìm các đoạn chứa tên + giá. Override nếu site có cấu trúc."""
        out = []
        # Tìm tên sản phẩm + giá gần nhau (rất heuristic)
        for m in re.finditer(r"(.{0,60}?" + re.escape(query.split()[0]) + r".{0,60}?)", html):
            snippet = m.group(1)
            pm = _PRICE_RE.search(snippet)
            if pm:
                price = float(pm.group(1).replace(".", "").replace(",", ""))
                out.append({"name": query, "price": price, "list_price": None})
                if len(out) >= 5:
                    break
        return out

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        from .collectors import _parse_pack_volume
        pack, vol = _parse_pack_volume(product_name)
        items = self.search(product_name, limit=5)
        if not items:
            return None
        price = items[0].get("price")
        if not price:
            return None
        promo = items[0].get("list_price")
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=self.base_channel, region_id="ONLINE",
            regular_price=float(price),
            promotion_price=float(promo) if promo else None,
            pack_quantity=pack, unit_volume_ml=vol, source=self.source, raw=items[0],
        )


class WinMartCollector(BaseRetailCollector):
    source = "winmart"
    base_channel = "WINMART"
    search_url = "https://winmart.vn/search?q={q}"


class BachHoaXanhCollector(BaseRetailCollector):
    source = "bachhoaxanh"
    base_channel = "BACHHOAXANH"
    search_url = "https://www.bachhoaxanh.com/tim-kiem?q={q}"


class AeonCollector(BaseRetailCollector):
    source = "aeon"
    base_channel = "AEON"
    search_url = "https://www.aeon.com.vn/search?q={q}"


class EmartCollector(BaseRetailCollector):
    source = "emart"
    base_channel = "EMART"
    search_url = "https://emart.com.vn/search?q={q}"


class CoopMartCollector(BaseRetailCollector):
    source = "coopmart"
    base_channel = "COOPMART"
    search_url = "https://cooponline.vn/search?q={q}"


class WebsosanhCollector(BaseRetailCollector):
    source = "websosanh"
    base_channel = "WEBSOSANH"
    search_url = "https://websosanh.vn/tim-kiem?q={q}"


class FacebookCollector(BaseRetailCollector):
    """Facebook không có API giá công khai + bot-protection -> stub."""
    source = "facebook"

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330):
        raise NotImplementedError(
            "Facebook không có API giá công khai và có bot-protection mạnh. "
            "Không khuyến nghị scrape làm nguồn giá chuẩn. Nếu cần, dùng "
            "Facebook Graph API (cần app review) hoặc đối tác.")


RETAIL_COLLECTORS = {
    "WINMART": WinMartCollector,
    "BACHHOAXANH": BachHoaXanhCollector,
    "AEON": AeonCollector,
    "EMART": EmartCollector,
    "COOPMART": CoopMartCollector,
    "WEBSOSANH": WebsosanhCollector,
    "FACEBOOK": FacebookCollector,
}


def collect_from_source(source_key: str, product_id: str, product_name: str) -> PricePoint | None:
    cls = RETAIL_COLLECTORS.get(source_key.upper())
    if not cls:
        return None
    try:
        return cls().collect(product_id, product_name)
    except NotImplementedError:
        raise
    except Exception as exc:
        log.warning("%s collect failed: %s", source_key, exc)
        return None


def collect_all_sources(product_id: str, product_name: str, path: str | None = None) -> dict[str, Any]:
    """Quét 1 sản phẩm qua mọi nguồn retail, lưu observation."""
    collected = 0
    failed = 0
    for key in RETAIL_COLLECTORS:
        try:
            pp = collect_from_source(key, product_id, product_name)
        except NotImplementedError:
            continue
        if pp:
            store_price_point(pp, path=path)
            collected += 1
        else:
            failed += 1
        time.sleep(_REQ_GAP_S)
    return {"source": "multi-retail", "collected": collected, "failed": failed}
