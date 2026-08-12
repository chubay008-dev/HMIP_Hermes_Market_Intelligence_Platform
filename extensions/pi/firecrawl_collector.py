"""firecrawl_collector.py — Nguồn giá thật qua Firecrawl Extract API.

Ưu điểm so với tự scrape Tiki:
- Firecrawl vượt được bot-protection (đã verify lấy được giá thật 598.800₫
  cho Heineken thùng 24 lon).
- Trả JSON có cấu trúc (name + price + currency) qua LLM extract → không
  cần parse HTML thủ công, ít nhiễu.
- Không cần proxy/residential IP tự mua.

Dùng làm nguồn CHÍNH thay thế demo (theo yêu cầu: không dùng data ảo).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from urllib.parse import quote as _urlquote

from .collectors import PricePoint, _parse_pack_volume, _REQ_GAP_S, store_price_point

log = logging.getLogger("hmip.firecrawl")

FIRECRAWL_API = "https://api.firecrawl.dev/v1/scrape"
_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                    "currency": {"type": "string"},
                },
            },
        }
    },
}


class FirecrawlCollector:
    source = "tiki-firecrawl"
    channel_id = "TIKI"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")

    def search(self, query: str) -> list[dict[str, Any]]:
        if not self.api_key:
            log.warning("Thiếu FIRECRAWL_API_KEY")
            return []
        try:
            r = requests.post(
                FIRECRAWL_API,
                json={
                    "url": f"https://tiki.vn/search?q={_urlquote(query)}",
                    "formats": ["extract"],
                    "extract": {"schema": _EXTRACT_SCHEMA},
                    "timeout": 30000,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60,
            )
            if r.status_code != 200:
                log.warning("Firecrawl HTTP %s: %s", r.status_code, r.text[:200])
                return []
            data = r.json().get("data", {})
            extract = data.get("extract") or data.get("json") or {}
            return extract.get("products", []) or []
        except Exception as exc:
            log.warning("Firecrawl error: %s", exc)
            return []

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        items = self.search(product_name)
        if not items:
            return None
        # Chọn item khớp nhất: chứa volume + tên sản phẩm
        vol = ref_vol
        best = None
        for it in items:
            n = (it.get("name") or "").lower()
            if f"{vol}ml" in n and product_name.split()[0].lower() in n:
                best = it
                break
        if not best:
            best = items[0]
        price = best.get("price")
        if not price:
            return None
        pack, v = _parse_pack_volume(best.get("name", product_name))
        promo = None  # Firecrawl extract thường chỉ trả giá hiện tại
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=self.channel_id, region_id="ONLINE",
            regular_price=float(price), promotion_price=promo,
            pack_quantity=pack, unit_volume_ml=v, source=self.source, raw=best,
        )


def collect_realtime_firecrawl(channel: str = "TIKI", limit: int | None = None,
                               path: str | None = None) -> dict[str, Any]:
    """Quét giá thật qua Firecrawl cho toàn bộ catalog."""
    from extensions.default_products import DEFAULT_PRODUCTS

    col = FirecrawlCollector()
    if not col.api_key:
        return {"channel": "firecrawl", "collected": 0, "failed": 0,
                "total": 0, "error": "no FIRECRAWL_API_KEY"}

    collected = failed = total = 0
    for pid, meta in list(DEFAULT_PRODUCTS.items())[:limit]:
        total += 1
        name = str(meta["product_name"])
        pp = col.collect(pid, name)
        if pp:
            store_price_point(pp, path=path)
            collected += 1
        else:
            failed += 1
        time.sleep(_REQ_GAP_S)
    return {"channel": "firecrawl", "collected": collected, "failed": failed, "total": total}
