# -*- coding: utf-8 -*-
"""Adapter Apify -> Shopee.vn qua actor 'xtracto~shopee-search' (trả VND thật).

Cần env APIFY_TOKEN (secret). Thiếu token -> SKIP, không fail pipeline.
Input actor: {"keyword": ..., "country": "vn", "maxItems": N, "sortType": 2}

Chạy:  APIFY_TOKEN=xxx python3 -m scripts.sources.apify_shopee
"""
from __future__ import annotations
import json
import os
import re
import time
import urllib.request

from .common import load_products, name_tokens, norm, save_raw

SOURCE = "shopee"
ACTOR = "xtracto~shopee-search"
RUN_SYNC = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"


def search(keyword: str, token: str, max_items: int = 15) -> list[dict]:
    body = {"keyword": keyword, "country": "vn", "maxItems": max_items,
            "sortType": 2}  # 2 = theo giá tăng dần -> lấy min thật
    req = urllib.request.Request(f"{RUN_SYNC}?token={token}",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=300).read())
        return d if isinstance(d, list) else []
    except Exception as e:
        print(f"  apify/shopee lỗi [{keyword}]: {e}")
        return []


def collect() -> list[dict]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("SKIP: thiếu APIFY_TOKEN — bỏ qua Shopee.")
        return []
    products = load_products()
    # Giới hạn số keyword mỗi lần để bảo vệ quota; ưu tiên SKU phổ biến.
    out = []
    for p in products[:10]:
        pid, name = p["id"], p["name"]
        q = re.sub(r"\s*\(.*?\)", "", name) + " bia"
        case = single = None
        for it in search(q, token):
            nm = norm(it.get("name") or "")
            price = it.get("price")
            if not isinstance(price, (int, float)) or price <= 0:
                continue
            toks = name_tokens(name)
            if toks and sum(1 for t in toks if t in nm) < max(1, len(toks) - 1):
                continue
            pr = int(price)
            # Giá >=150k mới coi là THÙNG (tránh nhầm "thùng" trong title combo với giá lẻ)
            is_case = ("thùng" in nm or "24 lon" in nm or "24 chai" in nm) and pr >= 150000
            if is_case:
                case = min(case, pr) if case else pr
            elif ("lon" in nm or "chai" in nm) and 6000 <= pr < 70000:
                single = min(single, pr) if single else pr
        if case or single:
            out.append({
                "product_id": pid, "name": name,
                "price_case_vnd": case,
                "price_single_vnd": single or (round(case/24/1000)*1000 if case else None),
                "source": SOURCE, "confidence": "low",   # giá shopee nhiễu sale
                "url": f"https://shopee.vn/search?keyword={re.sub(' ', '%20', q)}",
            })
        time.sleep(1.0)
    return out


def main():
    items = collect()
    if not items and not os.environ.get("APIFY_TOKEN"):
        return
    p = save_raw(SOURCE, items)
    print(f"apify/shopee: {len(items)} SKU -> {p}")


if __name__ == "__main__":
    main()
