"""
bia_parsers.py — Parser tách TÊN + GIÁ bia từ HTML của 4 site VN.

Mỗi site có cấu trúc HTML riêng:
- bianhagau.vn / vietgourmet.vn : WordPress + WooCommerce (chuẩn, dễ parse)
- beerhouse.vn                  : KiotViet theme, trang chủ hay để "Giá liên hệ"
- khotangbiabi.vn               : theme riêng, giá lazy-load bằng JS

Hàm chính: parse_products(url, html) -> list[{"name","price","currency","url"}]
- price: int (VND) hoặc None nếu "liên hệ"/không lấy được
- currency: "VND" | "₫" | None
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Product:
    name: str
    price: Optional[int]
    currency: Optional[str]
    url: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


_WOO_NAME = re.compile(
    r'class="[^"]*woocommerce-loop-product__title[^"]*"[^>]*>(.*?)</', re.S)
_WOO_NAME_ALT = re.compile(
    r'class="name product-title woocommerce-loop-product__title"[^>]*>(.*?)</', re.S)
_WOO_PRICE = re.compile(
    r'class="woocommerce-Price-amount amount"[^>]*>(.*?)</span>', re.S)
_WOO_PRICE_VND = re.compile(r'woocommerce-Price-currencySymbol[^>]*>(.*?)</span>', re.S)
_LINK_TITLE = re.compile(r'<a[^>]*\btitle="([^"]+)"', re.S)
_PROD_LINK = re.compile(r'<a[^>]*class="[^"]*woocommerce-LoopProduct-link[^"]*"[^>]*href="([^"]+)"', re.S)


def _clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").strip()


def _parse_price(raw: str) -> tuple[Optional[int], Optional[str]]:
    """raw dạng '1.680.000&nbsp;VND' hoặc '2.065.000₫' -> (1680000, 'VND')."""
    raw = _clean_text(raw)
    if not raw:
        return None, None
    cur = None
    m = re.search(r"(VND|₫|USD|\$)", raw, re.I)
    if m:
        cur = m.group(1).upper() if m.group(1).upper() != "₫" else "₫"
    num = re.sub(r"[^0-9]", "", raw)
    if not num:
        return None, cur
    return int(num), cur


# ----------------------------------------------------------------------------
# Parser từng site
# ----------------------------------------------------------------------------
def _parse_woocommerce(html: str) -> list[Product]:
    """Dùng chung cho bianhagau + vietgourmet (WooCommerce)."""
    # Tên: ưu tiên class name chuẩn, fallback aria-label link
    names = [_clean_text(x) for x in _WOO_NAME.findall(html) or _WOO_NAME_ALT.findall(html)]
    prices_raw = _WOO_PRICE.findall(html)
    links = _PROD_LINK.findall(html)

    # Nếu tên rỗng (lazy-load), thử aria-label của mọi link sản phẩm
    if not names:
        names = [m for m in re.findall(r'<a[^>]*aria-label="([^"]+)"[^>]*href="[^"]*product', html)][:len(prices_raw)] or names

    out: list[Product] = []
    n = max(len(names), len(prices_raw))
    for i in range(n):
        name = names[i] if i < len(names) else f"Sản phẩm #{i+1}"
        price = None
        cur = None
        if i < len(prices_raw):
            price, cur = _parse_price(prices_raw[i])
        url = links[i] if i < len(links) else None
        out.append(Product(name=name, price=price, currency=cur, url=url))
    return out


def _parse_beerhouse(html: str) -> list[Product]:
    """KiotViet theme. Giá dạng '695.000đ' trong .new-price / .price."""
    # Tên sản phẩm
    names = [_clean_text(x) for x in re.findall(
        r'class="product-title"[^>]*>(.*?)</', html, re.S)]
    if not names:
        names = [_clean_text(x) for x in _LINK_TITLE.findall(html)]

    # Giá: beerhouse dùng .new-price chứa '695.000đ' (chữ đ thường)
    price_blocks = re.findall(
        r'class="(?:new-price|old-price)[^"]*"[^>]*>(.*?)</', html, re.S)
    if not price_blocks:
        price_blocks = re.findall(
            r'class="[^"]*price[^"]*"[^>]*>(.*?)</', html, re.S)

    def _to_vnd(raw: str):
        raw = _clean_text(raw)
        if not raw or "liên hệ" in raw.lower():
            return None, None
        num = re.sub(r"[^0-9]", "", raw)
        return (int(num), "đ") if num else (None, None)

    out: list[Product] = []
    for i, name in enumerate(names):
        price = cur = None
        if i < len(price_blocks):
            price, cur = _to_vnd(price_blocks[i])
        out.append(Product(name=name or f"Sản phẩm #{i+1}",
                            price=price, currency=cur, url=None))
    return out


def _parse_khotangbiabi(html: str) -> list[Product]:
    """Theme riêng. Tên nằm trong slug URL sản phẩm, giá lazy-load/liên hệ.
    Ví dụ: /ban-bia.../bia-trai-cay-bi-st-louis-premium-framboise.html
    """
    # Tìm mọi link sản phẩm có slug bia
    items = re.findall(
        r'<a[^>]*href="(https?://khotangbiabi\.vn/[^"]*/(bia-[^"]+\.html))"', html)
    seen = set()
    out: list[Product] = []
    for full, slug in items:
        if slug in seen:
            continue
        seen.add(slug)
        # Tên từ slug: bỏ 'ban-bia...' prefix, thay - thành space
        parts = slug.split("/")[-1].replace(".html", "").split("-")
        # bỏ các prefix nhiễu
        name_parts = [w for w in parts if w not in ("ban", "bia") or len(parts) <= 2]
        # chỉ lấy từ đoạn có nghĩa: bỏ token đầu nếu là 'ban'/'bia' lặp
        name = " ".join(parts).strip()
        # Lấy chunk sau 'ban-bia...' nếu có
        m = re.search(r"ban-bia-[^/]*/(.+)\.html", slug)
        if m:
            name = m.group(1).replace("-", " ").strip()
        price = cur = None  # giá thường lazy-load/liên hệ
        out.append(Product(name=name or slug, price=price, currency=cur, url=full))
    return out


# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------
def parse_products(url: str, html: str) -> list[Product]:
    if "bianhagau" in url or "vietgourmet" in url:
        return _parse_woocommerce(html)
    if "beerhouse" in url:
        return _parse_beerhouse(html)
    if "khotangbiabi" in url:
        return _parse_khotangbiabi(html)
    # Mặc định thử wooCommerce
    return _parse_woocommerce(html)


def parse_to_dicts(url: str, html: str) -> list[dict]:
    return [p.to_dict() for p in parse_products(url, html)]
