"""jina_collector.py — Nguồn giá thật dự phòng qua Jina Reader (free).

Jina Reader (https://r.jina.ai/<url>) trả markdown sạch của bất kỳ URL nào
mà không cần browser/proxy. Dùng làm tier-3 fallback khi Tiki API bị block
và Firecrawl hết credit.

Pipeline:
  1. Lấy product URL từ Tiki API công khai (free).
  2. Wrap qua r.jina.ai/<product_url> -> markdown.
  3. Parse giá từ markdown (regex).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from .collectors import PricePoint, _parse_pack_volume, _REQ_GAP_S, store_price_point
from .normalization import normalize_price

log = logging.getLogger("hmip.jina")

JINA = "https://r.jina.ai/"
_TIKI_API = "https://tiki.vn/api/v2/products"
_PRICE_RE = re.compile(r"([\d][\d\.,]{2,})\s*(?:đ|VND|vnđ)", re.I)


class JinaCollector:
    source = "tiki-jina"
    channel_id = "TIKI"

    def search_product_url(self, query: str) -> tuple[str | None, str | None]:
        """Lấy (product_url, product_name) từ Tiki API công khai."""
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

    def scrape_price(self, product_url: str) -> float | None:
        try:
            r = requests.get(JINA + product_url, headers={"Accept": "text/plain"}, timeout=45)
            if r.status_code != 200:
                return None
            md = r.text
            prices = [float(x.replace(".", "").replace(",", "")) for x in _PRICE_RE.findall(md)]
            # lọc giá hợp lý (50k - 5tr cho 1 thùng bia)
            valid = [p for p in prices if 50000 <= p <= 5000000]
            return max(valid) if valid else (prices[0] if prices else None)
        except Exception as exc:
            log.warning("Jina err: %s", exc)
            return None

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330) -> PricePoint | None:
        url, real_name = self.search_product_url(product_name)
        if not url:
            return None
        price = self.scrape_price(url)
        if not price:
            return None
        pack, v = _parse_pack_volume(real_name or product_name)
        promo = None
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=self.channel_id, region_id="ONLINE",
            regular_price=float(price), promotion_price=promo,
            pack_quantity=pack, unit_volume_ml=v, source=self.source, raw={"url": url},
        )


def collect_realtime_jina(channel: str = "TIKI", limit: int | None = None,
                          path: str | None = None) -> dict[str, Any]:
    from extensions.default_products import DEFAULT_PRODUCTS
    col = JinaCollector()
    collected = failed = total = 0
    for pid, meta in list(DEFAULT_PRODUCTS.items())[:limit]:
        total += 1
        pp = col.collect(pid, str(meta["product_name"]))
        if pp:
            store_price_point(pp, path=path)
            collected += 1
        else:
            failed += 1
        time.sleep(_REQ_GAP_S * 2)
    return {"channel": "jina", "collected": collected, "failed": failed, "total": total}
