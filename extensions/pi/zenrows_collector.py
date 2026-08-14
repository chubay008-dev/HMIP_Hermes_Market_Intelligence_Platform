"""zenrows_collector.py — Nguồn giá thật qua ZenRows (render JS).

ZenRows render JavaScript của Tiki SPA qua headless browser, trả HTML/markdown
sau khi JS chạy xong → parse được giá thật.

Ưu điểm: vượt bot-protection, render JS, free tier 1000 credits/tháng.
Nhược điểm: js_render tốn 5x credits. Dùng làm tier 3 (sau ScraperAPI).

Config (env):
  ZENROWS_KEY        — API key từ app.zenrows.com
  ZENROWS_PREMIUM    — "true" để dùng residential proxy (nâng cao thành công)
  ZENROWS_CC         — country code proxy (mặc định "vn"; cần premium)
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote as _urlquote

import requests

from .collectors import PricePoint, _parse_pack_volume, _REQ_GAP_S, store_price_point
from .price_extract import extract_product_price

log = logging.getLogger("hmip.zenrows")

ZENROWS_ENDPOINT = "https://api.zenrows.com/v1/"


class ZenRowsCollector:
    source = "tiki-zenrows"
    channel_id = "TIKI"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ZENROWS_KEY", "")
        self.premium = os.getenv("ZENROWS_PREMIUM", "false").lower() in (
            "1", "on", "true", "yes")
        self.country_code = os.getenv("ZENROWS_CC", "vn")

    def scrape_html(self, target_url: str) -> str | None:
        """Gọi ZenRows render JS, trả HTML đã render (hoặc None khi lỗi)."""
        if not self.api_key:
            log.warning("Thiếu ZENROWS_KEY")
            return None
        params: dict[str, Any] = {
            "apikey": self.api_key,
            "url": target_url,
            "js_render": "true",
        }
        if self.premium:
            params["premium_proxy"] = "true"
            params["proxy_country"] = self.country_code
        try:
            r = requests.get(ZENROWS_ENDPOINT, params=params, timeout=60)
            if r.status_code != 200:
                if r.status_code == 402 or "credits" in r.text.lower():
                    log.error("ZenRows hết credit (402).")
                else:
                    log.warning("ZenRows HTTP %s: %s", r.status_code, r.text[:200])
                return None
            return r.text
        except Exception as exc:
            log.warning("ZenRows error: %s", exc)
            return None

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        search_url = f"https://tiki.vn/search?q={_urlquote(product_name)}"
        html = self.scrape_html(search_url)
        if not html:
            return None
        price = extract_product_price(html, brand=product_name)
        if not price:
            log.warning("ZenRows: không tìm thấy giá hợp lệ cho %s", product_name)
            return None
        pack, v = _parse_pack_volume(product_name)
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=self.channel_id, region_id="ONLINE",
            regular_price=float(price), promotion_price=None,
            pack_quantity=pack, unit_volume_ml=v, source=self.source,
            raw={"url": search_url},
        )


def collect_realtime_zenrows(channel: str = "TIKI", limit: int | None = None,
                             path: str | None = None) -> dict[str, Any]:
    """Quét giá thật qua ZenRows cho toàn bộ catalog."""
    from extensions.default_products import DEFAULT_PRODUCTS

    col = ZenRowsCollector()
    if not col.api_key:
        return {"channel": "zenrows", "collected": 0, "failed": 0,
                "total": 0, "error": "no ZENROWS_KEY"}

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
    return {"channel": "zenrows", "collected": collected, "failed": failed, "total": total}
