# -*- coding: utf-8 -*-
"""Adapter websosanh.vn — trang tổng hợp giá nhiều sàn (Tiki, Shopee, Lazada...).
Không cần JS, HTML tĩnh. Lấy giá min theo từ khóa tên sản phẩm.

Chạy:  python3 -m scripts.sources.websosanh
"""
from __future__ import annotations
import json
import re
import time
import urllib.parse
import urllib.request

from .common import UA, extract_vnd, load_products, name_tokens, norm, save_raw

SOURCE = "websosanh"


def search(query: str) -> str:
    url = "https://websosanh.vn/s/" + urllib.parse.quote(query) + ".htm"
    req = urllib.request.Request(url, headers=UA)
    try:
        return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  websosanh lỗi [{query}]: {e}")
        return ""


def parse_items(html: str, prod_name: str) -> list[tuple[str, int]]:
    """Trả list (item_name, price) từ khối product-single của websosanh.
    Mỗi item: <h2 class="product-single-name"><a href="/slug/so-sanh.htm">TÊN</a>
    ... <div class="product-single-price">Giá từ 300.000 đ</div>"""
    toks = name_tokens(prod_name)
    if not toks:
        return []
    out = []
    for m in re.finditer(
            r'product-single-name"><a href="(/[^"]+/so-sanh\.htm)"[^>]*>(.*?)</a>(.{0,400}?)'
            r'product-single-price">\s*Giá từ\s*([\d.,]+)', html, re.S):
        slug, name_html, _mid, price_txt = m.groups()
        item_name = re.sub(r"<[^>]+>", "", name_html).strip() or slug.replace("-", " ")
        item_n = norm(item_name + " " + slug)
        if sum(1 for t in toks if t in item_n) < max(1, len(toks) - 1):
            continue
        try:
            price = int(price_txt.replace(".", "").replace(",", ""))
        except ValueError:
            continue
        out.append((item_name, price))
    return out


def collect() -> list[dict]:
    out = []
    for p in load_products():
        pid, name = p["id"], p["name"]
        q = re.sub(r"\s*\(.*?\)", "", name)
        items = parse_items(search(q), name)
        prices = [pr for _n, pr in items]
        if prices:
            case = min(x for x in prices if x >= 150000) if any(x >= 150000 for x in prices) else None
            single = min(x for x in prices if 8000 <= x <= 120000) if any(8000 <= x <= 120000 for x in prices) else None
            if case or single:
                out.append({
                    "product_id": pid, "name": name,
                    "price_case_vnd": case,
                    "price_single_vnd": single or (round(case / 24 / 1000) * 1000 if case else None),
                    "source": SOURCE, "confidence": "medium",
                    "url": f"https://websosanh.vn/s/{urllib.parse.quote(q)}.htm",
                })
        time.sleep(0.4)
    return out


def main():
    items = collect()
    p = save_raw(SOURCE, items)
    print(f"websosanh: {len(items)} SKU -> {p}")


if __name__ == "__main__":
    main()
