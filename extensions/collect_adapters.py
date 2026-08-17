"""Collect adapters — nguồn giá cho task "collect" của WF-PRC-001.

HAI CHẾ ĐỘ, chọn bằng env `HMIP_COLLECT_MODE`:

1. "demo" (mặc định) — `SimulatedPriceAdapter`
   Sinh giá dao động ngẫu nhiên quanh một giá tham chiếu, cho các sản
   phẩm CÓ THẬT trong ontology (P123 Saigon, P456 Heineken). Dùng để
   chạy thử toàn hệ thống end-to-end mà không cần API bên ngoài.
   Đây KHÔNG phải giá thị trường thật — chỉ để demo luồng.

2. "http" — `HttpCollectAdapter`
   Gọi HTTP API thật. Cấu hình:
     HMIP_PRICE_API_BASE   ví dụ https://api.nhacungcap.vn/products
     HMIP_PRICE_API_KEY    (tuỳ chọn, gửi dạng Bearer)
     HMIP_PRICE_URL_TPL    (tuỳ chọn) template URL: {base}/{pid} mặc định
     HMIP_PRICE_FIELD_PRICE / _BRAND / _TITLE / _CURRENCY / _PROVINCE
                          (tuỳ chọn) chỉ định trường JSON nếu nguồn trả khác
   Kỳ vọng response JSON có trường price (số). Muốn nối Shopee/Tiki/nguồn
   nội bộ thì sửa `_parse_response()` hoặc set env HMIP_PRICE_FIELD_*.

Cả hai đều tuân thủ `BaseAdapter` protocol của HMIP: fetch() + health().
Core kernel KHÔNG bị sửa — đây chỉ là implementation cắm vào khe có sẵn.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any

import httpx

from core.exceptions import WorkflowExecutionException

COLLECT_MODE = os.getenv("HMIP_COLLECT_MODE", "demo").lower()
PRICE_API_BASE = os.getenv("HMIP_PRICE_API_BASE", "")
PRICE_API_KEY = os.getenv("HMIP_PRICE_API_KEY", "")
PRICE_URL_TPL = os.getenv("HMIP_PRICE_URL_TPL", "")  # mặc định: {base}/{pid}
# Cho phép nguồn trả tên trường khác (nối API bên thứ 3)
FIELD_PRICE = os.getenv("HMIP_PRICE_FIELD_PRICE", "price")
FIELD_BRAND = os.getenv("HMIP_PRICE_FIELD_BRAND", "brand")
FIELD_TITLE = os.getenv("HMIP_PRICE_FIELD_TITLE", "title")
FIELD_CURRENCY = os.getenv("HMIP_PRICE_FIELD_CURRENCY", "currency")
FIELD_PROVINCE = os.getenv("HMIP_PRICE_FIELD_PROVINCE", "province")

# Giá tham chiếu cho chế độ demo — khớp sản phẩm trong knowledge/master/.
# _DEMO_CATALOG = 2 SP gốc + toàn bộ DEFAULT_PRODUCTS (hardcode từ market map bia).
from extensions.default_products import DEFAULT_PRODUCTS

_DEMO_CATALOG: dict[str, dict[str, Any]] = {
    "P123": {
        "brand": "Bia Sài Gòn",
        "product_name": "Bia Sài Gòn Special 330ml",
        "ref_price": 18000.0,
        "province": "HCMC",
    },
    "P456": {
        "brand": "Heineken",
        "product_name": "Heineken Lager 330ml",
        "ref_price": 22000.0,
        "province": "HCMC",
    },
    **DEFAULT_PRODUCTS,
}


class SimulatedPriceAdapter:
    """Nguồn giá mô phỏng — dao động ±12% quanh giá tham chiếu.

    Biên độ ±12% cố ý vượt ngưỡng ALERT (5%) và chạm ESCALATE (10%),
    để thấy được cả 3 nhánh quyết định khi chạy nhiều lần.
    """

    def __init__(self, *, volatility: float = 0.12) -> None:
        self._volatility = volatility

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        product_id = str(request.get("product_id", ""))
        source = str(request.get("source", "demo"))
        entry = _DEMO_CATALOG.get(product_id)
        if entry is None:
            # Sản phẩm mới (thêm từ giao diện) không có trong catalog cứng:
            # sinh giá mô phỏng quanh mức mặc định để vẫn demo được.
            ref = float(os.getenv("HMIP_DEFAULT_BASE_PRICE", "18000"))
            name = str(request.get("product_name") or product_id)
            brand = str(request.get("brand") or "Unknown")
            swing = random.uniform(-self._volatility, self._volatility)
            price = round(ref * (1 + swing), 2)
            return {
                "brand": brand,
                "product_name": name,
                "price_text": f"{price:,.0f}",
                "currency": "VND",
                "store": source,
                "province": "N/A",
                "source_url": f"demo://simulated/{product_id}",
                "product_id": product_id,
                "source": source,
                "fetched_at": time.time(),
            }
        swing = random.uniform(-self._volatility, self._volatility)
        price = round(entry["ref_price"] * (1 + swing), 2)
        return {
            "brand": entry["brand"],
            "product_name": entry["product_name"],
            "price_text": f"{price:,.0f}",
            "currency": "VND",
            "store": source,
            "province": entry["province"],
            "source_url": f"demo://simulated/{product_id}",
            "product_id": product_id,
            "source": source,
            "fetched_at": time.time(),
        }

    def health(self) -> bool:
        return True


class HttpCollectAdapter:
    """Nguồn giá thật qua HTTP."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        product_id = str(request.get("product_id", ""))
        source = str(request.get("source", "api"))
        if not PRICE_API_BASE:
            raise WorkflowExecutionException(
                "HMIP_COLLECT_MODE=http nhưng chưa đặt HMIP_PRICE_API_BASE",
                code="COLLECT_PRICE_SOURCE_UNAVAILABLE",
            )
        base = PRICE_API_BASE.rstrip("/")
        if PRICE_URL_TPL:
            url = PRICE_URL_TPL.format(base=base, pid=product_id)
        else:
            url = f"{base}/{product_id}"
        headers = {"Accept": "application/json"}
        if PRICE_API_KEY:
            headers["Authorization"] = f"Bearer {PRICE_API_KEY}"
        try:
            resp = httpx.get(url, headers=headers, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise WorkflowExecutionException(
                f"collect: price API unavailable ({exc})",
                code="COLLECT_PRICE_SOURCE_UNAVAILABLE",
            ) from exc
        return self._parse_response(data, product_id, source, url)

    def _parse_response(
        self, data: dict[str, Any], product_id: str, source: str, url: str
    ) -> dict[str, Any]:
        """Điểm tuỳ biến khi nối nguồn thật — chỉnh mapping ở đây.

        Tên trường có thể cấu hình qua env HMIP_PRICE_FIELD_* để nối
        API bên thứ 3 không cần sửa code.
        """
        price = data.get(FIELD_PRICE)
        if price is None:
            raise WorkflowExecutionException(
                f"collect: response thiếu trường '{FIELD_PRICE}' cho {product_id}",
                code="COLLECT_PRICE_SOURCE_UNAVAILABLE",
            )
        return {
            "brand": data.get(FIELD_BRAND) or "Unknown",
            "product_name": data.get(FIELD_TITLE) or data.get("name") or product_id,
            "price_text": f"{float(price):,.0f}",
            "currency": data.get(FIELD_CURRENCY, "VND"),
            "store": source,
            "province": data.get(FIELD_PROVINCE, "N/A"),
            "source_url": url,
            "product_id": product_id,
            "source": source,
            "fetched_at": time.time(),
        }

    def health(self) -> bool:
        if not PRICE_API_BASE:
            return False
        try:
            return httpx.get(PRICE_API_BASE, timeout=5.0).status_code < 500
        except httpx.HTTPError:
            return False


def build_collect_adapter() -> Any:
    """Chọn adapter theo HMIP_COLLECT_MODE.

    - "http" + có HMIP_PRICE_API_BASE -> HttpCollectAdapter (API giá riêng).
    - "http" NHƯNG chưa đặt PRICE_API_BASE -> dùng Tiki thật (TikiCollector,
      API công khai FREE, không cần key) làm nguồn giá thật luôn.
    - mọi trường hợp khác -> SimulatedPriceAdapter (demo).
    """
    if COLLECT_MODE == "http":
        if PRICE_API_BASE:
            return HttpCollectAdapter()
        # Fallback: Tiki API công khai (free) làm nguồn giá thật.
        from extensions.pi import collectors as _col

        class _TikiRealAdapter:
            def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
                pid = str(request.get("product_id", ""))
                name = str(request.get("product_name") or request.get("brand") or pid)
                # Brand thật từ catalog mặc định (khớp ontology) — collector chỉ trả
                # channel/source, không biết brand nên không dùng làm brand record.
                from extensions.default_products import DEFAULT_PRODUCTS
                brand_name = DEFAULT_PRODUCTS.get(pid, {}).get("brand", "")
                pp = None
                # Tier 1: Tiki API công khai (nhanh, free) — hay bị block từ cloud IP
                try:
                    pp = _col.collect_product("TIKI", pid, name)
                except Exception as _e:
                    print(f"[collect] Tiki err: {_e}")
                # Tier 2: Firecrawl (có key trên Render) — scrape Tiki chuẩn, tin cậy
                if not pp:
                    try:
                        from .pi import firecrawl_collector as _fc
                        pp = _fc.FirecrawlCollector().collect(pid, name)
                    except Exception as _e:
                        print(f"[collect] Firecrawl err: {_e}")
                # Tier 3: ScraperAPI (render JS, vượt bot-protection) — thêm vào
                # chain vì Jina Reader không render JS, hay miss giá trên SPA Tiki.
                if not pp:
                    try:
                        from .pi import scraperapi_collector as _sa
                        pp = _sa.ScraperAPICollector().collect(pid, name)
                    except Exception as _e:
                        print(f"[collect] ScraperAPI err: {_e}")
                # Tier 4: ZenRows (render JS, fallback khi ScraperAPI hết credit)
                if not pp:
                    try:
                        from .pi import zenrows_collector as _zr
                        pp = _zr.ZenRowsCollector().collect(pid, name)
                    except Exception as _e:
                        print(f"[collect] ZenRows err: {_e}")
                # Tier 5: Jina scrape Tiki search (free, fallback cuối) — thử 2 lần
                # vì Jina hay transient fail / rate-limit trên shared IP (Render).
                if not pp:
                    from .pi import jina_collector as _jc
                    for _attempt in (1, 2):
                        try:
                            pp = _jc.JinaCollector().collect(pid, name)
                            if pp:
                                break
                        except Exception as _e:
                            print(f"[collect] Jina err (try {_attempt}): {_e}")
                        if _attempt == 1:
                            time.sleep(2)
                if not pp:
                    raise WorkflowExecutionException(
                        f"collect: không lấy được giá Tiki cho {pid} ({name})",
                        code="COLLECT_PRICE_SOURCE_UNAVAILABLE",
                    )
                eff = pp.promotion_price or pp.regular_price
                # base_price (ref_price) là giá 1 LON; pp.eff là giá PACK (thùng hoặc
                # lon tuỳ item match). Chuẩn hoá về giá/lon để so sánh apples-to-apples:
                # chia pack_quantity (24 cho thùng, 1 cho lon lẻ) — tránh variance
                # khổng lồ khi lấy giá thùng ~400k vs base lon ~38k (→ ESCALATE sai).
                pack = pp.pack_quantity if pp.pack_quantity and pp.pack_quantity > 0 else 1
                # Heuristic bảo vệ: collector HTML (Jina/ZenRows/ScraperAPI) parse
                # pack từ tên config (lon=1) vì không có item name, nhưng
                # extract_product_price có thể lấy giá THÙNG (~400k+). Nếu eff >
                # 100000 mà pack==1 → gần như chắc chắn là thùng → suy pack từ tỷ số
                # giá thùng/base (snap về 6/12/24) thay vì /24 cứng (PR #11). /24 cứng
                # sai khi SP là thùng 6 hoặc 12 lon → giá/lon lệch → ESCALATE sai.
                if pack == 1 and eff > 100000:
                    base = float(DEFAULT_PRODUCTS.get(pid, {}).get("ref_price", 0) or 0)
                    if base > 0:
                        from extensions.pi.price_extract import _infer_pack_from_price
                        inferred = _infer_pack_from_price(eff, base)
                        if inferred:
                            pack = inferred
                    if pack == 1:
                        pack = 24  # fallback cuối: thùng bia VN thường 24 lon
                unit_price = eff / pack
                return {
                    "brand": brand_name,
                    "product_name": name,
                    "price_text": f"{unit_price:,.0f}",
                    "currency": "VND",
                    "store": "tiki",
                    "province": pp.region_id,
                    "source_url": f"https://tiki.vn/search?q={name}",
                    "product_id": pid,
                    "source": "tiki",
                    "fetched_at": time.time(),
                }

            def health(self) -> bool:
                return True

        return _TikiRealAdapter()
    return SimulatedPriceAdapter()


def make_collect_handler() -> Any:
    adapter = build_collect_adapter()

    def handler(task_input: dict[str, Any], context: Any) -> dict[str, Any]:
        # Inject tên/brand từ DB nếu sản phẩm được thêm từ giao diện
        # (dùng cho SP mới không có trong catalog cứng của demo adapter)
        from extensions import db

        pid = str(task_input.get("product_id", ""))
        if not task_input.get("product_name"):
            for p in db.get_products():
                if p["id"] == pid:
                    task_input = {**task_input,
                                  "product_name": p.get("name"),
                                  "brand": p.get("brand")}
                    break
        return adapter.fetch(task_input)

    return handler


def make_collect_rollback() -> Any:
    def rollback(compensation_context: dict[str, Any]) -> None:
        return None  # collect là bước đầu, chưa có side effect

    return rollback
