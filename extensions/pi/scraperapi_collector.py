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
from .price_extract import extract_product_price

log = logging.getLogger("hmip.scraperapi")

SCRAPERAPI_ENDPOINT = "http://api.scraperapi.com"


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

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        search_url = f"https://tiki.vn/search?q={_urlquote(product_name)}"
        html = self.scrape_html(search_url)
        if not html:
            return None
        price = extract_product_price(html, brand=product_name)
        if not price:
            log.warning("ScraperAPI: không tìm thấy giá hợp lệ cho %s", product_name)
            return None
        pack, v = _parse_pack_volume(product_name)
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=self.channel_id, region_id="ONLINE",
            regular_price=float(price), promotion_price=None,
            pack_quantity=pack, unit_volume_ml=v, source=self.source,
            raw={"url": search_url},
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
