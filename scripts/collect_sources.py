#!/usr/bin/env python3
"""collect_sources.py — Chạy mọi adapter nguồn, ghi raw vào data/raw/<source>.json.

Mỗi adapter tự xử lý lỗi riêng, adapter nào fail không chặn adapter khác.
Thiếu token (vd APIFY_TOKEN) -> adapter tự SKIP.

Chạy:  python3 scripts/collect_sources.py [websosanh sendo apify_shopee ...]
"""
from __future__ import annotations
import importlib
import sys

DEFAULT = ["websosanh", "sendo", "apify_shopee"]


def main():
    targets = sys.argv[1:] or DEFAULT
    ok, failed = [], []
    for name in targets:
        try:
            mod = importlib.import_module(f"scripts.sources.{name}")
            mod.main()
            ok.append(name)
        except Exception as e:
            failed.append((name, str(e)))
            print(f"FAIL {name}: {e}", file=sys.stderr)
    print(f"\nHoàn thành: {len(ok)} nguồn OK, {len(failed)} fail")
    if failed:
        print("Fail:", ", ".join(n for n, _ in failed))


if __name__ == "__main__":
    main()
