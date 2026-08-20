# -*- coding: utf-8 -*-
"""Adapter Sendo.vn — API search công khai (JSON, không cần key, giống Tiki API).

Chạy:  python3 -m scripts.sources.sendo
"""
from __future__ import annotations
import json
import re
import time
import urllib.parse
import urllib.request

from .common import UA, load_products, save_raw

SOURCE = "sendo"
API = "https://www.sendo.vn/m/wap_v2/search/suggest?q={q}"


def search(query: str) -> list[dict]:
    url = API.format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers=UA)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
        return (d.get("data") or {}).get("product") or []
    except Exception as e:
        print(f"  sendo lỗi [{query}]: {e}")
        return []


def collect() -> list[dict]:
    out = []
    for p in load_products():
        pid, name = p["id"], p["name"]
        q = re.sub(r"\s*\(.*?\)", "", name) + " bia"
        case = single = None
        for it in search(q):
            pr = it.get("final_price") or it.get("price")
            nm = (it.get("name") or "").lower()
            if not pr:
                continue
            is_case = "thùng" in nm or "24 lon" in nm or "24 chai" in nm
            if is_case:
                case = min(case, pr) if case else pr
            elif ("lon" in nm or "chai" in nm) and pr < 70000:
                single = min(single, pr) if single else pr
        if case or single:
            out.append({
                "product_id": pid, "name": name,
                "price_case_vnd": case,
                "price_single_vnd": single or (round(case / 24 / 1000) * 1000 if case else None),
                "source": SOURCE, "confidence": "medium",
                "url": f"https://www.sendo.vn/tim-kiem?q={urllib.parse.quote(q)}",
            })
        time.sleep(0.3)
    return out


def main():
    items = collect()
    p = save_raw(SOURCE, items)
    print(f"sendo: {len(items)} SKU -> {p}")


if __name__ == "__main__":
    main()
