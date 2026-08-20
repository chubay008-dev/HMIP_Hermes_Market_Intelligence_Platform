# -*- coding: utf-8 -*-
"""Adapter bachhoanhaveo.com — probe 20/08/2026 cho thấy HTML tĩnh có giá thật.
Phát hiện khi tra nguồn ngoại lệ; khác với bachhoaxanh (SPA).

Chạy:  python3 -m scripts.sources.bachhoanhaveo
"""
from __future__ import annotations
import re
import time
import urllib.parse
import urllib.request
from .common import UA, extract_vnd, load_products, name_tokens, norm, save_raw

SOURCE = "bachhoanhaveo"


def search(query: str) -> str:
    url = "https://bachhoanhaveo.com/search?q=" + urllib.parse.quote(query)
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  bachhoanhaveo lỗi [{query}]: {e}")
        return ""


def parse(html: str, prod_name: str) -> list[int]:
    toks = name_tokens(prod_name)
    if not toks:
        return []
    out = []
    # bachhoanhaveo có cụm giá trong HTML tĩnh
    for block in re.findall(r'class="[^"]*(?:product|item)[^"]*"[^>]*>(.{0,800}?)</', html, re.S):
        if sum(1 for t in toks if t in norm(block)) < max(1, len(toks) - 1):
            continue
        out += extract_vnd(block)
    return out


def collect() -> list[dict]:
    out = []
    for p in load_products():
        pid, name = p["id"], p["name"]
        q = re.sub(r"\s*\(.*?\)", "", name)
        prices = parse(search(q), name)
        if prices:
            case = min(x for x in prices if x >= 150000) if any(x >= 150000 for x in prices) else None
            single = min(x for x in prices if 8000 <= x <= 120000) if any(8000 <= x <= 120000 for x in prices) else None
            if case or single:
                out.append({
                    "product_id": pid, "name": name,
                    "price_case_vnd": case,
                    "price_single_vnd": single or (round(case/24/1000)*1000 if case else None),
                    "source": SOURCE, "confidence": "medium",
                    "url": f"https://bachhoanhaveo.com/search?q={urllib.parse.quote(q)}",
                })
        time.sleep(0.3)
    return out


def main():
    items = collect()
    p = save_raw(SOURCE, items)
    print(f"bachhoanhaveo: {len(items)} SKU -> {p}")


if __name__ == "__main__":
    main()
