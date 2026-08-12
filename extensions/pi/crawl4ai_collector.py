"""crawl4ai_collector.py — Nguồn giá thật dự phòng tier-4 qua Crawl4AI (self-host).

Crawl4AI là crawler mã nguồn mở (thay thế Firecrawl tự host, free). Dùng
headless browser render JS của Tiki SPA, parse giá từ raw HTML (JSON embed).

Ưu điểm: không phụ thuộc credit Firecrawl/Jina, tự chủ hoàn toàn.
Nhược điểm: cần cài chromium (~115MB) + chạy browser (nặng hơn Jina).
Dùng làm tier 4 (cuối cùng) khi Tiki API + Firecrawl + Jina đều fail.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import requests

from .collectors import PricePoint, _parse_pack_volume, _REQ_GAP_S, store_price_point

log = logging.getLogger("hmip.crawl4ai")

_TIKI_API = "https://tiki.vn/api/v2/products"
_PRICE_RE = re.compile(r'"price"\s*:\s*(\d+)')


def _get_product_url(query: str) -> tuple[str | None, str | None]:
    try:
        r = requests.get(_TIKI_API, params={"q": query, "limit": 1},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if r.status_code != 200:
            return None, None
        items = r.json().get("data", [])
        if not items:
            return None, None
        p = items[0]
        return "https://tiki.vn/" + (p.get("url_path") or ""), p.get("name")
    except Exception as exc:
        log.warning("Tiki API err: %s", exc)
        return None, None


async def _crawl_price(product_url: str) -> float | None:
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
    except ImportError:
        log.warning("crawl4ai chưa cài -> bỏ qua tier 4")
        return None
    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, word_count_threshold=0)
    async with AsyncWebCrawler() as crawler:
        res = await crawler.arun(product_url, config=cfg)
        if not res.success:
            return None
        html = res.html or ""
        prices = [int(x) for x in _PRICE_RE.findall(html)]
        valid = [p for p in prices if 50000 <= p <= 5000000]
        return max(valid) if valid else (prices[0] if prices else None)


class Crawl4AICollector:
    source = "tiki-crawl4ai"
    channel_id = "TIKI"

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        url, real_name = _get_product_url(product_name)
        if not url:
            return None
        try:
            price = asyncio.run(_crawl_price(url))
        except Exception as exc:
            log.warning("Crawl4AI err: %s", exc)
            return None
        if not price:
            return None
        pack, v = _parse_pack_volume(real_name or product_name)
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=self.channel_id, region_id="ONLINE",
            regular_price=float(price), promotion_price=None,
            pack_quantity=pack, unit_volume_ml=v, source=self.source, raw={"url": url},
        )


def collect_realtime_crawl4ai(channel: str = "TIKI", limit: int | None = None,
                              path: str | None = None) -> dict[str, Any]:
    from extensions.default_products import DEFAULT_PRODUCTS
    col = Crawl4AICollector()
    collected = failed = total = 0
    for pid, meta in list(DEFAULT_PRODUCTS.items())[:limit]:
        total += 1
        pp = col.collect(pid, str(meta["product_name"]))
        if pp:
            store_price_point(pp, path=path)
            collected += 1
        else:
            failed += 1
        time.sleep(_REQ_GAP_S)
    return {"channel": "crawl4ai", "collected": collected, "failed": failed, "total": total}
