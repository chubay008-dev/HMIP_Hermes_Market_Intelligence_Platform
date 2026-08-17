"""price_extract.py — Tiện ích trích giá sản phẩm VN từ HTML/markdown.

Dùng chung cho mọi collector scrape HTML (ScraperAPI, ZenRows, Jina).
Lọc nhiễu: bỏ qua số kèm token "phút/phí/ship..." (hotline, phí ship, lượt
đánh giá). Chỉ giữ giá hợp lệ cho 1 lon/thùng bia VN (5.000₫ - 2.000.000₫).

Pack-aware (PR #9): ngoài việc ưu tiên nhóm giá LON (≤ LON_MAX), module còn
parse pack_quantity từ context HTML gần mỗi giá ("thùng 24 lon", "24 chai",
"x24", "lon 24"...) để chuẩn hoá giá THÙNG về giá/LON ngay tại đây. Khi trang
search chỉ có item THÙNG (Sư Tử Trắng, Huda — lon lẻ hết hàng), extract trả
giá/lon chính xác thay vì giá thùng (trước đây adapter phải heuristic /24,
hay sai lệch). Adapter heuristic /24 chỉ còn là lưới an toàn cuối.
"""

from __future__ import annotations

import re

_PRICE_RE = re.compile(r"([\d][\d\.,]{2,})\s*(?:đ|VND|vnđ|₫)", re.I)
_NOISE_TOKENS = ("phút", "phí", "ship", "đánh giá", "lượt", "review", "đã bán", "sold")

MIN_PRICE = 5000.0
MAX_PRICE = 2_000_000.0
# Giá 1 lon bia VN tối đa ~50.000đ (bia cao cấp). Giá > LON_MAX gần như chắc
# chắn là thùng/pack — khi trang search có cả lon lẻ + thùng, ưu tiên lon để
# so sánh apples-to-apples với base_price (ref_price là giá 1 lon).
LON_MAX = 50000.0
# Ngưỡng giá được coi là THÙNG: > BOX_MIN gần như chắc chắn là giá thùng/pack
# (lon bia VN tối đa ~50k). Dùng để kích hoạt parse pack khi không có giá lon.
BOX_MIN = 100000.0
# Số lon/thùng phổ biến nhất ở VN — fallback khi context không nêu rõ pack
# (Tiki thường bán thùng 24 lon). Chỉ dùng khi giá rõ ràng là thùng (> BOX_MIN).
DEFAULT_BOX_PACK = 24
# Window ký tự SAU giá để tìm pack token. Tên sản phẩm/pack thường đứng
# ngay sau giá trên trang search Tiki (vd "598.800₫ HEINEKEN ### Thùng 24").
# KHÔNG dùng window trước — tránh bắt pack token của sản phẩm trước đó (bleed).
_PACK_CTX_AFTER = 32

# Mẫu pack: "thùng 24", "thùng 24 lon", "24 lon", "lon 24", "x24", "24 chai",
# "vỉ 6", "pack 6"... Trả số lon/chai trong pack.
_PACK_PATTERNS = [
    re.compile(r"th[uù]ng\s*(\d{1,3})\s*(?:lon|chai|cu)?", re.I),
    re.compile(r"(\d{1,3})\s*lon", re.I),
    re.compile(r"(\d{1,3})\s*chai", re.I),
    re.compile(r"lon\s*(\d{1,3})", re.I),
    re.compile(r"x\s*(\d{1,3})\b", re.I),
    re.compile(r"(\d{1,3})\s*[x*]\s*(?:lon|chai)", re.I),
    re.compile(r"v[iỉ]\s*(\d{1,3})", re.I),
    re.compile(r"pack\s*(\d{1,3})", re.I),
]
_PACK_MIN = 2
_PACK_MAX = 48


def _median(values: list[float]) -> float:
    values.sort()
    return values[len(values) // 2]


def _detect_pack(ctx: str) -> int | None:
    """Trích pack_quantity từ context HTML quanh một giá.

    VD: "598.800₫ HEINEKEN ### Thùng 24 lon" → 24; "12 lon bia" → 12.
    Chỉ nhận số trong [2,48] — tránh nhận nhầm số khác (volume, rating...).
    """
    for pat in _PACK_PATTERNS:
        m = pat.search(ctx)
        if m:
            try:
                n = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if _PACK_MIN <= n <= _PACK_MAX:
                return n
    return None


def _pick_price(values: list[float]) -> float:
    """Ưu tiên nhóm giá LON (≤ LON_MAX) nếu có — tránh lấy thùng khi có lon lẻ.

    Trang search Tiki thường có cả lon lẻ (~18-40k) và thùng (~400-700k).
    base_price là giá lon nên phải lấy lon. Nếu không có lon → fallback
    median toàn bộ (thùng) — caller nên chia pack (parse từ context).
    """
    lon = [v for v in values if v <= LON_MAX]
    if lon:
        return _median(lon)
    return _median(values)


def _infer_pack_from_price(box_price: float, base_price: float) -> int | None:
    """Suy pack_quantity từ tỷ số giá thùng / giá lon (base).

    base_price là giá 1 LON đã biết (ref_price từ catalog). Nếu collector
    cào được giá THÙNG nhưng context HTML không nêu rõ pack (không có
    "thùng 24 lon"), dùng tỷ số box/base để suy pack. Snap về 6/12/24
    (pack bia VN phổ biến) gần nhất — chính xác hơn /24 cứng (PR #9 chỉ
    chia 24, sai khi SP là thùng 6 hoặc 12 lon).

    VD: box=736000, base=30667 → ratio≈24 → pack 24.
        box=360000, base=30000 → ratio≈12 → pack 12.
        box=108000, base=18000 → ratio≈6  → pack 6.
    """
    if not base_price or base_price <= 0:
        return None
    ratio = box_price / base_price
    if ratio < _PACK_MIN:
        return None  # gần base → chắc là lon lẻ, không phải thùng
    # Snap về pack phổ biến gần nhất (6/12/24). Cho phép sai số ±30%.
    best = None
    best_diff = float("inf")
    for cand in (6, 12, 24):
        diff = abs(ratio - cand) / cand
        if diff < 0.30 and diff < best_diff:
            best, best_diff = cand, diff
    return best


def _resolve_base_price(product_id: str, product_name: str) -> float | None:
    """Lấy giá 1 LON (ref_price) từ catalog DEFAULT_PRODUCTS.

    Dùng để suy pack từ tỷ số giá thùng/base khi context HTML không nêu pack.
    Trả None nếu không có catalog hoặc SP không trong catalog.
    """
    try:
        from extensions.default_products import DEFAULT_PRODUCTS
        meta = DEFAULT_PRODUCTS.get(product_id)
        if meta:
            rp = meta.get("ref_price")
            if rp and float(rp) > 0:
                return float(rp)
    except Exception:
        pass
    return None


def extract_product_price(html_or_md: str,
                          min_price: float = MIN_PRICE,
                          max_price: float = MAX_PRICE,
                          brand: str | None = None,
                          base_price: float | None = None) -> float | None:
    """Trích giá sản phẩm hợp lệ từ HTML/markdown Tiki.

    Bỏ qua các số kèm token nhiễu (vd "1000 đ/phút" hotline).

    Pack-aware (PR #9 + PR #11): khi giá trùng brand/toàn trang đều là THÙNG
    (> LON_MAX), parse pack_quantity từ context gần giá ("thùng 24 lon"...)
    và trả giá/LON thay vì giá thùng. Khi context KHÔNG nêu pack, nếu
    ``base_price`` (giá 1 lon đã biết) được truyền → suy pack từ tỷ số
    box/base (snap về 6/12/24) — chính xác hơn /24 cứng. Điều này sửa dứt
    điểm mismatch thùng/lon cho SP chỉ có item thùng trên Tiki (Sư Tử Trắng,
    Huda) — trước đây trả giá thùng → adapter heuristic /24 hay lệch khi
    SP là thùng 6 hoặc 12 lon → ESCALATE sai liên tục (spam notify).

    Args:
        html_or_md: HTML/markdown trang search Tiki.
        min_price/max_price: khoảng giá hợp lệ (5k-2tr).
        brand: tên thương hiệu/sản phẩm mục tiêu — ưu tiên giá có brand keyword
            gần, tránh lấy median toàn trang.
        base_price: giá 1 LON đã biết (ref_price từ catalog). Dùng để suy pack
            khi context HTML không nêu rõ pack. None = bỏ qua fallback này.

    Trả về:
    - Giá/LON nếu có giá lon lẻ HOẶC pack phát hiện được (context hoặc
      price-based inference).
    - Fallback: median thùng (caller/adapter sẽ heuristic /DEFAULT_BOX_PACK).
    """
    candidates: list[float] = []
    brand_matches: list[float] = []
    # Ghi (price, pack) cho mỗi ứng viên thùng để fallback chia pack chính xác.
    box_with_pack: list[tuple[float, int]] = []
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
        # Context SAU giá để tìm pack token (tên SP/pack đứng sau giá trên
        # trang search Tiki, vd "598.800₫ HEINEKEN ### Thùng 24"). Không
        # dùng window trước để tránh bắt pack của sản phẩm khác (bleed).
        ctx_wide = html_or_md[m.end(): m.end() + _PACK_CTX_AFTER].lower()
        is_brand = bool(primary_kw and primary_kw in
                        html_or_md[m.end(): m.end() + 30].lower())
        if is_brand:
            brand_matches.append(val)
        # Lưu pack cho mọi giá thùng (cả brand + non-brand) để fallback chia.
        if val > LON_MAX:
            pack = _detect_pack(ctx_wide)
            if pack:
                box_with_pack.append((val, pack))
    pool = brand_matches if brand_matches else candidates
    if not pool:
        return None
    # 1) Ưu tiên giá LON nếu có (lon lẻ trên trang search).
    lon_pool = [v for v in pool if v <= LON_MAX]
    if lon_pool:
        return _median(lon_pool)
    # 2) Chỉ có giá THÙNG → chuẩn hoá về giá/LON bằng pack phát hiện được.
    box_pool = (box_with_pack if brand_matches
                else [b for b in box_with_pack if b[0] in pool])
    if box_pool:
        per_lon = [v / p for v, p in box_pool if p > 0]
        if per_lon and all(LON_MAX * 0.1 <= x <= LON_MAX for x in per_lon):
            return round(_median(per_lon), 2)
    # 3) Context KHÔNG nêu pack → suy pack từ tỷ số giá thùng/base (nếu có
    #    base_price). Chính xác hơn /24 cứng khi SP là thùng 6/12 lon.
    box_prices = [v for v in pool if v > LON_MAX]
    if box_prices and base_price and base_price > 0:
        inferred = [_infer_pack_from_price(v, base_price) for v in box_prices]
        per_lon = [v / p for v, p in zip(box_prices, inferred, strict=True)
                   if p and p > 0]
        if per_lon and all(LON_MAX * 0.1 <= x <= LON_MAX for x in per_lon):
            return round(_median(per_lon), 2)
    # 4) Fallback cuối: median thùng (caller/adapter sẽ heuristic /DEFAULT_BOX_PACK).
    return _median(pool)
