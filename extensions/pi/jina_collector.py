"""jina_collector.py — Nguồn giá thật dự phòng qua Jina Reader (free).

Jina Reader (https://r.jina.ai/<url>) trả markdown sạch của bất kỳ URL nào
mà không cần browser/proxy. Dùng làm tier-4 fallback khi Firecrawl/ScraperAPI/
ZenRows đều fail.

GIỚI HẠN: Jina Reader KHÔNG render JavaScript. Tiki là SPA → trang search/
product KHÔNG chứa giá sản phẩm trong HTML tĩnh, chỉ có text như hotline
"1000 đ/phút". Module này lọc nhiễu để KHÔNG ghi giá rác: chỉ trả giá khi
tìm thấy số hợp lệ (5k-2tr) không kèm token "phút/phí/ship...". Trên thực
tế Jina thường trả None cho Tiki → tier này chỉ dự phòng cuối, không đáng
tin cậy bằng ScraperAPI/ZenRows (có render JS).

Pipeline:
  1. Wrap URL Tiki search qua r.jina.ai/<url> -> markdown.
  2. Parse giá từ markdown bằng _extract_product_price (lọc nhiễu hotline).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .collectors import PricePoint, _parse_pack_volume, _REQ_GAP_S, store_price_point
from .price_extract import extract_product_price, _resolve_base_price

log = logging.getLogger("hmip.jina")

JINA = "https://r.jina.ai/"
_TIKI_API = "https://tiki.vn/api/v2/products"


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

    def scrape_price(self, product_url: str, brand: str | None = None,
                     product_id: str | None = None) -> float | None:
        """Scrape Tiki qua Jina Reader, trả giá sản phẩm hợp lệ (hoặc None).

        Jina Reader KHÔNG render JS → trang search/product Tiki (SPA) không
        chứa giá sản phẩm, chỉ có static text như "1000 đ/phút" hotline.
        Dùng extract_product_price để lọc nhiễu: chỉ trả giá khi tìm thấy
        số hợp lệ (5k-2tr) KHÔNG kèm token "phút/phí/ship...". Nếu trang
        chỉ có hotline → trả None (không ghi giá rác).

        brand: tên sản phẩm mục tiêu → ưu tiên giá có brand keyword gần
        (tránh lấy median của toàn bộ sản phẩm trên trang search).
        product_id: truyền để resolve base_price từ catalog → suy pack từ
        tỷ số giá thùng/base khi context HTML không nêu rõ pack (PR #11).
        """
        try:
            r = requests.get(JINA + product_url, headers={"Accept": "text/plain"}, timeout=45)
            if r.status_code != 200:
                return None
            base = _resolve_base_price(product_id, brand or "") if product_id else None
            return extract_product_price(r.text, brand=brand, base_price=base)
        except Exception as exc:
            log.warning("Jina err: %s", exc)
            return None

    def collect(self, product_id: str, product_name: str, ref_vol: int = 330,
                channel=None) -> PricePoint | None:
        # Jina scrape trang search kênh (mặc định TIKI) trực tiếp qua r.jina.ai.
        from .channels import get_channel
        chan = channel or get_channel("TIKI")
        search_url = chan.search_url(product_name)
        price = self.scrape_price(search_url, brand=product_name, product_id=product_id)
        if not price:
            return None
        pack, v = _parse_pack_volume(product_name)
        promo = None
        return PricePoint(
            product_id=product_id, sku_id=f"SKU-{product_id}",
            channel_id=chan.channel_id, region_id="ONLINE",
            regular_price=float(price), promotion_price=promo,
            pack_quantity=pack, unit_volume_ml=v,
            source=f"{chan.channel_id.lower()}-jina", raw={"url": search_url},
        )


def collect_realtime_jina(channel: str = "TIKI", limit: int | None = None,
                          path: str | None = None,
                          channels: list | None = None) -> dict[str, Any]:
    from extensions.default_products import DEFAULT_PRODUCTS
    from .channels import get_channel
    col = JinaCollector()
    chan_list = channels or [get_channel(channel)]
    collected = failed = total = 0
    for chan in chan_list:
        for pid, meta in list(DEFAULT_PRODUCTS.items())[:limit]:
            total += 1
            pp = col.collect(pid, str(meta["product_name"]), channel=chan)
            if pp:
                store_price_point(pp, path=path)
                collected += 1
            else:
                failed += 1
            time.sleep(_REQ_GAP_S * 2)
    return {"channel": "jina", "collected": collected, "failed": failed, "total": total}
