# -*- coding: utf-8 -*-
"""Adapter Tiki.vn — API public JSON, không cần key.
Nguồn tin cậy (confidence high trong schema cũ).

Chạy:  python3 -m scripts.sources.tiki
"""
from __future__ import annotations
import json
import re
import time
import urllib.parse
import urllib.request

from .common import load_products, save_raw

SOURCE = "tiki"


def search(query: str) -> list[dict]:
    url = "https://tiki.vn/api/v2/products?q=" + urllib.parse.quote(query) + "&limit=12"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
        return d.get("data", []) or []
    except Exception as e:
        print(f"  tiki lỗi [{query}]: {e}")
        return []


def collect() -> list[dict]:
    out = []
    for p in load_products():
        pid, name = p["id"], p["name"]
        q = re.sub(r"\d+\s*ml", "", name, flags=re.I)
        q = re.sub(r"\(khong con\)|không cồn|0\.0", "", q, flags=re.I).strip()
        case = single = None
        for it in search(q):
            nm = (it.get("name") or "").lower()
            price = it.get("price")
            if not price:
                continue
            is_case = "thùng" in nm or "chục" in nm or "24 lon" in nm or "24 chai" in nm
            if is_case and "24" in nm:
                case = min(case, price) if case else price
            elif ("lon" in nm or "chai" in nm) and not is_case and price < 70000:
                single = min(single, price) if single else price
        if case or single:
            out.append({
                "product_id": pid, "name": name,
                "price_case_vnd": case,
                "price_single_vnd": single or (round(case/24/1000)*1000 if case else None),
                "source": SOURCE, "confidence": "high",
                "url": f"https://tiki.vn/search?q={urllib.parse.quote(q)}",
            })
        time.sleep(0.25)
    return out


def main():
    items = collect()
    p = save_raw(SOURCE, items)
    print(f"tiki: {len(items)} SKU -> {p}")


if __name__ == "__main__":
    main()
