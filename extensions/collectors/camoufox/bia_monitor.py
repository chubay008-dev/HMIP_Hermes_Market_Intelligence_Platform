"""
bia_monitor.py — Hệ thống giám sát giá bia từ 4 site VN.

Luồng:
  1. Quét 4 site bằng Camoufox (scrape_many / scrape_age_gate)
  2. Parse tên + giá bằng bia_parsers
  3. Lưu lịch sử giá vào SQLite (bia_prices.db)
  4. (Tùy chọn) in bảng so sánh / phát hiện thay đổi giá

Thiết kế:
  - Bảng products : thông tin tĩnh (site, name, url, sku_key)
  - Bảng price_history : mỗi lần quét 1 dòng (product_id, price, scraped_at)
  - sku_key = hash(name) để theo dõi cùng 1 sản phẩm qua ngày

Chạy:
  source /home/kali/camoufox-venv/bin/activate
  python bia_monitor.py            # quét 1 lần + lưu DB
  python bia_monitor.py --report   # in bảng so sánh giá hôm nay
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import asyncio
from datetime import datetime, date
from typing import Optional

from camoufox_scraper import scrape_many_sync, scrape_age_gate
from bia_parsers import parse_products

DB_PATH = "bia_prices.db"
AGE_GATE_SITE = "vietgourmet.vn"

# Mỗi site: danh sách URL cần quét (trang chủ hoặc trang danh mục có giá)
SITE_URLS = {
    "https://khotangbiabi.vn": [
        "https://khotangbiabi.vn/cac-loai-bia-bi-nhe-do/",
        "https://khotangbiabi.vn/cac-loai-bia-bi-trung-do/",
        "https://khotangbiabi.vn/cac-loai-bia-bi-nang-do/",
    ],
    "https://beerhouse.vn": [
        "https://beerhouse.vn/danh-muc/bia-pho-thong/",
        "https://beerhouse.vn/danh-muc/bia-bi/",
        "https://beerhouse.vn/danh-muc/bia-duc/",
    ],
    "https://bianhagau.vn": ["https://bianhagau.vn"],
    "https://vietgourmet.vn": ["https://vietgourmet.vn"],
}
# Flatten danh sách URL quét tuần tự (giữ site gốc để parse)
URL_TO_SITE = {u: s for s, urls in SITE_URLS.items() for u in urls}


# ----------------------------------------------------------------------------
# DB schema
# ----------------------------------------------------------------------------
def init_db(path: str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute(
        """CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            site TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT,
            UNIQUE(site, sku_key)
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            price INTEGER,
            currency TEXT,
            scraped_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )"""
    )
    con.commit()
    return con


def _key(name: str) -> str:
    return hashlib.md5(name.strip().lower().encode("utf-8")).hexdigest()[:12]


# ----------------------------------------------------------------------------
# Quét + lưu
# ----------------------------------------------------------------------------
def run_scan(con: sqlite3.Connection) -> dict:
    # Quét song song các URL thường (không cửa tuổi)
    normal_urls = [u for u, s in URL_TO_SITE.items() if AGE_GATE_SITE not in s]
    results = scrape_many_sync(normal_urls, wait_for="networkidle", retries=3)
    # vietgourmet riêng (cửa tuổi) — có thể có nhiều URL nhưng site này chỉ 1
    vg_urls = [u for u, s in URL_TO_SITE.items() if AGE_GATE_SITE in s]
    vg_results = [asyncio.run(scrape_age_gate(u)) for u in vg_urls]
    all_res = results + vg_results

    today = datetime.now().isoformat(timespec="seconds")
    stats = {"sites": 0, "products": 0, "priced": 0, "new": 0}
    cur = con.cursor()

    for r in all_res:
        site = URL_TO_SITE.get(r.url, r.url)
        if not r.ok:
            print(f"  [SKIP] {r.url} lỗi: {r.error}")
            continue
        stats["sites"] += 1
        prods = parse_products(site, r.html or "")
        for p in prods:
            if not p.name:
                continue
            k = _key(p.name)
            row = cur.execute(
                "SELECT id FROM products WHERE site=? AND sku_key=?", (r.url, k)
            ).fetchone()
            if row:
                pid = row[0]
            else:
                cur.execute(
                    "INSERT INTO products(site, sku_key, name, url) VALUES(?,?,?,?)",
                    (r.url, k, p.name, p.url),
                )
                pid = cur.lastrowid
                stats["new"] += 1
            # Dedup: chỉ lưu 1 bản ghi giá mỗi ngày cho mỗi sản phẩm
            day = today[:10]
            exists = cur.execute(
                "SELECT 1 FROM price_history WHERE product_id=? AND scraped_at>=?",
                (pid, day),
            ).fetchone()
            if not exists:
                cur.execute(
                    "INSERT INTO price_history(product_id, price, currency, scraped_at) VALUES(?,?,?,?)",
                    (pid, p.price, p.currency, today),
                )
            stats["products"] += 1
            if p.price is not None:
                stats["priced"] += 1
    con.commit()
    return stats


# ----------------------------------------------------------------------------
# Báo cáo
# ----------------------------------------------------------------------------
def print_report(con: sqlite3.Connection, days: int = 1):
    today = date.today().isoformat()
    rows = con.execute(
        """SELECT p.site, p.name, h.price, h.currency, h.scraped_at
           FROM price_history h JOIN products p ON p.id = h.product_id
           WHERE h.scraped_at >= ?
           ORDER BY p.site, p.name""",
        (today,),
    ).fetchall()
    print(f"\n=== GIÁ BIA HÔM NAY ({today}) ===")
    cur_site = None
    for site, name, price, cur, ts in rows:
        if site != cur_site:
            print(f"\n--- {site} ---")
            cur_site = site
        pr = f"{price:,} {cur}" if price is not None else "Giá liên hệ"
        print(f"  {name[:50]:50s} | {pr}")


def price_changes(con: sqlite3.Connection) -> list:
    """Phát hiện sản phẩm tăng/giảm giá so với lần quét gần nhất trước."""
    rows = con.execute(
        """SELECT p.site, p.name,
                  (SELECT price FROM price_history h2
                     WHERE h2.product_id=p.id ORDER BY h2.scraped_at DESC LIMIT 1) AS last_p,
                  (SELECT price FROM price_history h2
                     WHERE h2.product_id=p.id ORDER BY h2.scraped_at DESC LIMIT 1 OFFSET 1) AS prev_p
           FROM products p"""
    ).fetchall()
    changes = []
    for site, name, last_p, prev_p in rows:
        if last_p is not None and prev_p is not None and last_p != prev_p:
            changes.append((site, name, prev_p, last_p, last_p - prev_p))
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="In bảng giá hôm nay")
    ap.add_argument("--changes", action="store_true", help="In sản phẩm đổi giá")
    args = ap.parse_args()

    con = init_db()
    if not args.report and not args.changes:
        print("== Quét giá 4 site bằng Camoufox ==")
        stats = run_scan(con)
        print(f"Kết quả: {stats['sites']} site, {stats['products']} sản phẩm "
              f"({stats['priced']} có giá), {stats['new']} sản phẩm mới")
        print_report(con)
    if args.report:
        print_report(con)
    if args.changes:
        ch = price_changes(con)
        print("\n=== SẢN PHẨM ĐỔI GIÁ ===")
        for site, name, old, new, diff in ch:
            arrow = "▲" if diff > 0 else "▼"
            print(f"  {arrow} {name[:45]:45s} {old:,} -> {new:,} ({site})")
    con.close()


if __name__ == "__main__":
    main()
