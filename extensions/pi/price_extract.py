"""price_extract.py — Tiện ích trích giá sản phẩm VN từ HTML/markdown.

Dùng chung cho mọi collector scrape HTML (ScraperAPI, ZenRows, Jina).
Lọc nhiễu: bỏ qua số kèm token "phút/phí/ship..." (hotline, phí ship, lượt
đánh giá). Chỉ giữ giá hợp lệ cho 1 lon/thùng bia VN (5.000₫ - 2.000.000₫).
"""

from __future__ import annotations

import re

_PRICE_RE = re.compile(r"([\d][\d\.,]{2,})\s*(?:đ|VND|vnđ|₫)", re.I)
_NOISE_TOKENS = ("phút", "phí", "ship", "đánh giá", "lượt", "review", "đã bán", "sold")

MIN_PRICE = 5000.0
MAX_PRICE = 2_000_000.0


def extract_product_price(html_or_md: str,
                          min_price: float = MIN_PRICE,
                          max_price: float = MAX_PRICE,
                          brand: str | None = None) -> float | None:
    """Trích giá sản phẩm hợp lệ từ HTML/markdown Tiki.

    Bỏ qua các số kèm token nhiễu (vd "1000 đ/phút" hotline).

    Trả về:
    - Nếu có ``brand`` (tên thương hiệu/sản phẩm mục tiêu): ưu tiên giá có
      brand keyword xuất hiện gần (trong 60 ký tự xung quanh). Tránh lấy
      median của toàn bộ sản phẩm trên trang search (bia ngũ hành, Habeco,
      Rooster...). Nếu không khớp brand → fallback median.
    - Nếu không có brand: trả median của các ứng viên hợp lệ.
    """
    candidates: list[float] = []
    brand_matches: list[float] = []
    # Dùng các keyword riêng biệt từ brand (tên sản phẩm) để match linh hoạt —
    # vd "Heineken Lager 330ml" → ["heineken", "lager", "330ml"]. Giá match khi
    # CỦA keyword đầu tiên (tên thương hiệu) xuất hiện trong context gần.
    brand_kw = brand.lower().split() if brand else None
    primary_kw = brand_kw[0] if brand_kw else None
    for m in _PRICE_RE.finditer(html_or_md):
        ctx_after = html_or_md[m.end(): m.end() + 12].lower()
        ctx_before = html_or_md[max(0, m.start() - 12): m.start()].lower()
        if any(tok in ctx_before + ctx_after for tok in _NOISE_TOKENS):
            continue
        raw = m.group(1).replace(".", "").replace(",", "").replace("₫", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        if not (min_price <= val <= max_price):
            continue
        candidates.append(val)
        if primary_kw:
            # Chỉ kiểm tra context SAU giá (tên sản phẩm/brand thường đứng sau
            # giá trên trang search Tiki, vd "598.800₫ HEINEKEN ### Thùng").
            # Window hẹp 30 ký tự để tránh bắt giá của sản phẩm khác đứng gần.
            ctx_after_wide = html_or_md[m.end(): m.end() + 30].lower()
            if primary_kw in ctx_after_wide:
                brand_matches.append(val)
    if brand_matches:
        brand_matches.sort()
        return brand_matches[len(brand_matches) // 2]
    if not candidates:
        return None
    candidates.sort()
    return candidates[len(candidates) // 2]
