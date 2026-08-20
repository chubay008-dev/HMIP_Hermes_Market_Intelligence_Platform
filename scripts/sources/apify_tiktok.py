# -*- coding: utf-8 -*-
"""Adapter Apify -> TikTok Shop qua actor 'pratikdani~tiktok-shop-search-scraper'.

Thực tế probe (20/08/2026): actor trả về merch/hàng C2C in logo bia (quần áo,
ly, ốp lưng), không phải bia uống. Giá rác nhiễu -> adapter tự SKIP, giữ
skeleton để mở lại nếu có actor tốt hơn.

Cần env APIFY_TOKEN. Thiếu token -> SKIP, không fail pipeline.

Chạy:  APIFY_TOKEN=xxx python3 -m scripts.sources.apify_tiktok
"""
from __future__ import annotations
import os
from .common import save_raw

SOURCE = "tiktok"
ACTOR = "pratikdani~tiktok-shop-search-scraper"


def collect() -> list[dict]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("SKIP: thiếu APIFY_TOKEN — bỏ qua TikTok.")
        return []
    # Probe 20/08/2026: kết quả chỉ là merchandise in logo, không phải bia.
    print("SKIP tiktok: actor trả merch (đồ thun bia), không phải giá bia uống.")
    return []


def main():
    items = collect()
    if not items and not os.environ.get("APIFY_TOKEN"):
        return
    p = save_raw(SOURCE, items)
    print(f"apify/tiktok: {len(items)} SKU (SKIP) -> {p}")


if __name__ == "__main__":
    main()
