"""scraperapi_collector.py — Nguồn giá thật qua ScraperAPI (render JS).

ScraperAPI dùng headless browser render JavaScript của Tiki SPA, trả HTML
sau khi JS chạy xong → parse được giá thật (khác Jina Reader chỉ lấy HTML
tĩnh không có giá).

Ưu điểm: vượt bot-protection, render JS, có free tier 5000 requests/tháng.
Nhược điểm: mỗi request render tốn 10 credits (500 requests/tháng free).
Dùng làm tier 2 (sau Firecrawl) khi Firecrawl hết credit.

Config (env):
  SCRAPERAPI_KEY     — API key từ dashboard.scraperapi.com
  SCRAPERAPI_CC      — country code (mặc định "vn" cho thị trường VN)
  SCRAPERAPI_PREMIUM — "true" để dùng residential proxy (nâng cao thành công)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import quote as _urlquote

import requests

from .collectors import PricePoint, _parse_pack_volume, _REQ_GAP_S, store_price_point

log = logging.getLogger("hmip.scraperapi")

SCRAPERAPI_ENDPOINT = "http://api.scraperapi.com"

# Stopwords — từ phổ biến không đặc trưng brand, bỏ qua khi match tên sản phẩm.
_STOPWORDS = {
    "bia", "beer", "lon", "chai", "lon", "ml", "l", "thùng", "thung", "x",
    "lager", "special", "export", "gold", "black", "bạc", "bac", "premium",
    "super", "dry", "ichiban", "extra", "stout", "draft", "draught", "crystal",
    "tail", "330", "330ml", "450", "450ml", "440", "440ml", "500ml", "330ml/lon",
    "white", "blanche", "witbier", "blonde", "hefe", "weiss", "weissbier",
}


def _brand_keywords(product_name: str) -> list[str]:
    """Trích keyword ĐẶC TRƯNG từ tên sản phẩm (bỏ stopword).

    VD "Bia Sài Gòn Special 330ml" → ["sài", "gòn"]; "Heineken Lager 330ml" → ["heineken"].
    Dùng để match item trong Tiki API result — tránh match nhầm sang bia khác.
    """
    kws = [w.lower().strip(".,()/-") for w in product_name.lower().split()]
    return [w for w in kws if w and w not in _STOPWORDS]


class ScraperAPICollector:
    source = "tiki-scraperapi"
    channel_id = "TIKI"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("SCRAPERAPI_KEY", "")
        self.country_code = os.getenv("SCRAPERAPI_CC", "vn")
        self.premium = os.getenv("SCRAPERAPI_PREMIUM", "false").lower() in (
            "1", "on", "true", "yes")

    def scrape_html(self, target_url: str) -> str | None:
        """Gọi ScraperAPI render JS, trả HTML đã render (hoặc None khi lỗi)."""
        if not self.api_key:
            log.warning("Thiếu SCRAPERAPI_KEY")
            return None
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "url": target_url,
            "render": "true",
            "country_code": self.country_code,
        }
        if self.premium:
            params["premium"] = "true"
        try:
            r = requests.get(SCRAPERAPI_ENDPOINT, params=params, timeout=60)
            if r.status_code != 200:
                if r.status_code == 402 or "credits" in r.text.lower():
                    log.error("ScraperAPI hết credit (402).")
                else:
                    log.warning("ScraperAPI HTTP %s: %s", r.status_code, r.text[:200])
                return None
            return r.text
        except Exception as exc:
            log.warning("ScraperAPI error: %s", exc)
            return None

    def _api_search(self, query: str, limit: int = 10) -> list[dict[str, Any]] | None:
        """Gọi Tiki public API qua ScraperAPI (render=false, 1 credit/call).

        Tiki SPA chặn /api/v2/products trực tiếp (403), nhưng ScraperAPI proxy
        bypass được. Trả JSON danh sách sản phẩm với giá thật chính xác.
        """
        if not self.api_key:
            log.warning("Thiếu SCRAPERAPI_KEY")
            return None
        api_url = f"https://tiki.vn/api/v2/products?q={_urlquote(query)}&limit={limit}"
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "url": api_url,
            "render": "false",
            "country_code": self.country_code,
        }
        if self.premium:
            params["premium"] = "true"
        try:
            r = requests.get(SCRAPERAPI_ENDPOINT, params=params, timeout=60)
            if r.status_code != 200:
                if r.status_code == 402 or "credits" in r.text.lower():
                    log.error("ScraperAPI hết credit (402).")
                else:
                    log.warning("ScraperAPI API HTTP %s: %s", r.status_code, r.text[:200])
                return None
            data = r.json()
            return data.get("data", []) or []
        except Exception as exc:
            log.warning("ScraperAPI API error: %s", exc)
            return None

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        items = self._api_search(product_name, limit=10)
        if not items:
            return None
        kws = _brand_keywords(product_name)
        _cfg_pack, cfg_vol = _parse_pack_volume(product_name)
        # Ưu tiên lon lẻ (pack=1) để so sánh apples-to-apples với base_price (lon).
        best = None
        for it in items:
            name = str(it.get("name", "")).lower()
            price = it.get("price")
            if price is None or price <= 0:
                continue
            if kws and not any(k in name for k in kws):
                continue
            pack, v = _parse_pack_volume(it.get("name") or product_name)
            if best is None or pack < best[0]:
                best = (pack, v, it, float(price))
        if not best:
            log.warning("ScraperAPI: không match sản phẩm %s trong %d kết quả", product_name, len(items))
            return None
        pack, v, it, price = best
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=self.channel_id, region_id="ONLINE",
            regular_price=price, promotion_price=None,
            pack_quantity=pack, unit_volume_ml=v or cfg_vol or ref_vol, source=self.source,
            raw={"url": f"tiki://product/{it.get('id')}", "name": it.get("name", "")},
        )


def collect_realtime_scraperapi(channel: str = "TIKI", limit: int | None = None,
                                path: str | None = None) -> dict[str, Any]:
    """Quét giá thật qua ScraperAPI cho toàn bộ catalog."""
    from extensions.default_products import DEFAULT_PRODUCTS

    col = ScraperAPICollector()
    if not col.api_key:
        return {"channel": "scraperapi", "collected": 0, "failed": 0,
                "total": 0, "error": "no SCRAPERAPI_KEY"}

    collected = failed = total = 0
    for pid, meta in list(DEFAULT_PRODUCTS.items())[:limit]:
        total += 1
        name = str(meta["product_name"])
        pp = col.collect(pid, name)
        if not pp:
            time.sleep(_REQ_GAP_S)
            pp = col.collect(pid, name)
        if pp:
            store_price_point(pp, path=path)
            collected += 1
        else:
            failed += 1
        time.sleep(_REQ_GAP_S * 2)
    return {"channel": "scraperapi", "collected": collected, "failed": failed, "total": total}
