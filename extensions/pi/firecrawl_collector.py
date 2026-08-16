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

    # Circuit breaker: set True khi API trả 402 (hết credit). Trong cùng
    # runtime, search() sẽ trả [] ngay để collect_smart skip sang tier khác,
    # tránh đốt thời gian gọi 68 lần timeout. Reset = restart process.
    _credit_exhausted: bool = False

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")

    def search(self, query: str) -> list[dict[str, Any]]:
        if not self.api_key:
            log.warning("Thiếu FIRECRAWL_API_KEY")
            return []
        if FirecrawlCollector._credit_exhausted:
            log.info("Firecrawl skip (circuit breaker: hết credit trong runtime này)")
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
                if r.status_code == 402:
                    log.error("Firecrawl HẾT CREDIT (402). Cần nạp tại firecrawl.dev/pricing. Dừng quét để tránh đốt credit.")
                    # Circuit breaker: flag tắt Firecrawl cho runtime hiện tại.
                    # collect_smart sẽ skip tier này và xuống ScraperAPI/ZenRows/Jina.
                    # Firecrawl tự bật lại khi credit refresh (402 → 200) sau khi
                    # process restart (Render free restart mỗi 15p, hoặc manual).
                    FirecrawlCollector._credit_exhausted = True
                else:
                    log.warning("Firecrawl HTTP %s: %s", r.status_code, r.text[:200])
                return []
            # Thành công → credit đã có lại (sau khi refresh 14/09) → reset flag.
            if FirecrawlCollector._credit_exhausted:
                log.info("Firecrawl credit đã có lại (200 OK) → reset circuit breaker")
                FirecrawlCollector._credit_exhausted = False
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
        # Matching chặt: ưu tiên item chứa brand + volume đúng.
        vol = ref_vol
        brand = product_name.split()[0].lower()  # từ đầu tiên thường là brand (Heineken, Tiger,...)
        best = None
        # Pass 1: có brand + volume
        for it in items:
            n = (it.get("name") or "").lower()
            if brand in n and f"{vol}ml" in n:
                best = it
                break
        # Pass 2: chỉ cần brand
        if not best:
            for it in items:
                n = (it.get("name") or "").lower()
                if brand in n:
                    best = it
                    break
        # Pass 3: fallback item đầu
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
        # Retry 1 lần nếu fail (tránh Firecrawl transient)
        if not pp:
            time.sleep(_REQ_GAP_S)
            pp = col.collect(pid, name)
        if pp:
            store_price_point(pp, path=path)
            collected += 1
        else:
            failed += 1
            log.warning("Firecrawl no price for %s (%s)", pid, name)
        time.sleep(_REQ_GAP_S * 2)  # Tiki/Firecrawl rate-limit: gap dài hơn
    return {"channel": "firecrawl", "collected": collected, "failed": failed, "total": total}
