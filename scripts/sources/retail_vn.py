# -*- coding: utf-8 -*-
"""Adapter bachhoaxanh / lotte / emart — siêu thị VN (Hướng B mở rộng).

Thực tế probe (20/08/2026):
  - bachhoaxanh.com  -> SPA (JS-rendered), HTML tĩnh không có giá -> SKIP
  - lotte.vn         -> DNS không resolve từ runner (geo-block) -> SKIP
  - emart.com.vn     -> SSL hostname mismatch -> SKIP

Giữ skeleton để bổ sung khi có headless browser/proxy. Adapter tự SKIP
an toàn, không chặn pipeline.

Chạy:  python3 -m scripts.sources.retail_vn
"""
from __future__ import annotations
from .common import save_raw

SOURCE = "retail_vn"   # bachhoaxanh | lotte | emart


def collect() -> list[dict]:
    # HTML tĩnh không render được giá; các sàn này là SPA hoặc geo-block.
    # Trả rỗng — reconcile sẽ dùng channels lịch sử + nguồn khác.
    print("SKIP retail_vn: bachhoaxanh/lotte/emart là SPA/geo-block, chưa cào tĩnh được.")
    return []


def main():
    p = save_raw(SOURCE, collect())
    print(f"retail_vn: 0 SKU (SKIP) -> {p}")


if __name__ == "__main__":
    main()
