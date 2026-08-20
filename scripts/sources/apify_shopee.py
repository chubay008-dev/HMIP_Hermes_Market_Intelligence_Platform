# -*- coding: utf-8 -*-
"""Adapter Apify -> Shopee.vn qua actor scraper của Apify.
Cần env APIFY_TOKEN (secret trong workflow). Dùng actor công khai phổ biến
'happyshoppers~shopee-scraper' chạy theo keyword.

Thiếu token -> SKIP, không fail pipeline.

Chạy:  APIFY_TOKEN=xxx python3 -m scripts.sources.apify_shopee
"""
from __future__ import annotations
import json
import os
import re
import time
import urllib.parse
import urllib.request

from .common import UA, load_products, save_raw

SOURCE = "shopee"
# actor Shopee scraper phổ biến trên Apify Store; thay bằng actor khác nếu cần
ACTOR = "happyshoppers~shopee-scraper"
API = "https://api.apify.com/v2"


def run_actor(products: list[dict], token: str) -> list[dict]:
    kws = [re.sub(r"\s*\(.*?\)", "", p["name"]) + " bia" for p in products]
    body = {
        "keyword": kws[0],           # chạy từng keyword (kws[0]) để giữ quota; có thể mở rộng
        "maxItems": 20,
        "sortType": 2,               # theo giá tăng dần -> lấy min thật
        "countryCode": "VN",
    }
    results = []
    for kw in kws:
        b = dict(body, keyword=kw)
        req = urllib.request.Request(
            f"{API}/acts/{ACTOR}/runs?token={token}",
            data=json.dumps(b).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            run = json.loads(urllib.request.urlopen(req, timeout=60).read())
            run_id = run["data"]["id"]
            for _ in range(24):  # poll tối đa ~4 phút
                time.sleep(10)
                st = json.loads(urllib.request.urlopen(
                    f"{API}/actor-runs/{run_id}?token={token}", timeout=30).read())
                if st["data"]["status"] in ("SUCCEEDED", "FAILED", "ABORTED"):
                    break
            if st["data"]["status"] != "SUCCEEDED":
                continue
            items = json.loads(urllib.request.urlopen(
                f"{API}/datasets/{st['data']['defaultDatasetId']}/items?token={token}",
                timeout=60).read())
            results.append({"keyword": kw, "items": items})
        except Exception as e:
            print(f"  apify/shopee lỗi [{kw}]: {e}")
    return results


def map_to_products(results: list[dict], products: list[dict]) -> list[dict]:
    from .common import name_tokens, norm
    out = []
    by_pid = {p["id"]: p for p in products}
    for block in results:
        best_pid, best_price = None, None
        for it in block["items"]:
            name = norm(it.get("name") or it.get("productName") or "")
            price = it.get("price") or it.get("priceMin")
            if not price:
                continue
            for pid, prod in by_pid.items():
                toks = name_tokens(prod["name"])
                if toks and sum(1 for t in toks if t in name) >= max(1, len(toks) - 1):
                    pr = int(float(price))
                    is_case = "thùng" in name
                    if best_pid is None or best_pid == pid:
                        best_pid = pid
                        best_price = min(best_price, pr) if best_price else pr
                        if best_price not in [x.get("price_case_vnd") for x in out] or not is_case:
                            pass
                    if not any(x["product_id"] == pid for x in out):
                        out.append({
                            "product_id": pid, "name": prod["name"],
                            "price_case_vnd": pr if is_case else None,
                            "price_single_vnd": None if is_case else pr,
                            "source": SOURCE, "confidence": "medium",
                            "url": it.get("item_url") or it.get("url"),
                        })
                    break
    return out


def main():
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("SKIP: thiếu APIFY_TOKEN — bỏ qua Shopee.")
        return
    products = load_products()
    results = run_actor(products[:8], token)  # tránh cháy quota — bắt đầu với SKU phổ biến
    items = map_to_products(results, products)
    p = save_raw(SOURCE, items)
    print(f"apify/shopee: {len(items)} SKU -> {p}")


if __name__ == "__main__":
    main()
