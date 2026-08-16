"""db.py — SQLite persistence cho lịch sử giá (fix: workflow chạy xong là mất).

Tầng lưu trữ này HOÀN TOÀN ĐỘC LẬP với core kernel. Web API / CLI đọc
ghi ở đây; kernel không biết nó tồn tại. Đây là cách đúng để thêm
persistence mà không phá ranh giới "core không phụ thuộc domain".

Schema:
  products(id, name, brand, source, base_price, created_at)
  price_points(id, product_id, price, currency, captured_at, decision,
               delta_percent, source_url)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from extensions.db_backend import connect as _backend_connect, is_postgres, session as _backend_session

DEFAULT_DB_PATH = os.getenv("HMIP_DB_PATH", "hmip.db")


def _connect(path: str = DEFAULT_DB_PATH):
    return _backend_connect(path, "DATABASE_URL")


def init_db(path: str | None = None) -> None:
    if path is None:
        path = DEFAULT_DB_PATH
    conn = _connect(path)
    pg = is_postgres("DATABASE_URL")
    schema = """
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                brand TEXT,
                source TEXT,
                base_price REAL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS price_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT,
                captured_at TEXT NOT NULL,
                decision TEXT,
                delta_percent REAL,
                source_url TEXT,
                province TEXT,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            CREATE INDEX IF NOT EXISTS idx_pp_product ON price_points(product_id);
            """
    if pg:
        schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    conn.executescript(schema)
    # migration: add province column if older DB lacks it
    cols = conn.table_columns("price_points")
    if "province" not in cols:
        try:
            conn.add_column("price_points", "province TEXT")
        except Exception:
            pass  # already exists
    conn.commit()
    conn.close()


def _session(path: str = DEFAULT_DB_PATH):
    return _backend_session(path, "DATABASE_URL")


def upsert_product(
    product_id: str,
    name: str,
    brand: str | None,
    source: str,
    base_price: float | None = None,
    path: str | None = None,
) -> None:
    """Ghi/Upsert sản phẩm. Nếu base_price=None và SP chưa có, để trống
    (sẽ được tự động gán từ lần quét đầu qua set_base_price_if_absent)."""
    if path is None:
        path = DEFAULT_DB_PATH
    now = datetime.now(timezone.utc).isoformat()
    with _session(path) as c:
        c.execute(
            """INSERT INTO products (id, name, brand, source, base_price, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, brand=excluded.brand,
                 source=excluded.source,
                 base_price=COALESCE(excluded.base_price, products.base_price)""",
            (product_id, name, brand, source, base_price, now),
        )


def record_price_point(
    product_id: str,
    price: float,
    currency: str | None,
    decision: str | None,
    delta_percent: float | None,
    source_url: str | None,
    province: str | None = None,
    path: str | None = None,
) -> int:
    if path is None:
        path = DEFAULT_DB_PATH
    now = datetime.now(timezone.utc).isoformat()
    # carry forward the last known province if caller omitted it (scans may not supply one)
    if province is None:
        with _session(path) as c:
            row = c.execute(
                "SELECT province FROM price_points WHERE product_id=? AND province IS NOT NULL ORDER BY id DESC LIMIT 1",
                (product_id,),
            ).fetchone()
            if row:
                province = row["province"]
    with _session(path) as c:
        if is_postgres("DATABASE_URL"):
            row = c.execute(
                """INSERT INTO price_points
                   (product_id, price, currency, captured_at, decision,
                    delta_percent, source_url, province)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (product_id, price, currency, now, decision, delta_percent, source_url, province),
            ).fetchone()
            return int(row["id"]) if row else 0
        cur = c.execute(
            """INSERT INTO price_points
               (product_id, price, currency, captured_at, decision,
                delta_percent, source_url, province)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (product_id, price, currency, now, decision, delta_percent, source_url, province),
        )
        return int(cur.lastrowid)


def get_base_price(product_id: str, path: str | None = None) -> float | None:
    """Đọc base_price đã lưu của sản phẩm (mốc tự động từ lần quét đầu)."""
    if path is None:
        path = DEFAULT_DB_PATH
    with _session(path) as c:
        row = c.execute(
            "SELECT base_price FROM products WHERE id=?", (product_id,)
        ).fetchone()
    return float(row["base_price"]) if row and row["base_price"] is not None else None


def set_base_price_if_absent(
    product_id: str, price: float, path: str | None = None
) -> float:
    """Nếu SP chưa có base_price, gán = price (lần quét đầu làm mốc).
    Trả về base_price hiện tại (đã có hoặc vừa gán)."""
    if path is None:
        path = DEFAULT_DB_PATH
    existing = get_base_price(product_id, path)
    if existing is not None:
        return existing
    with _session(path) as c:
        c.execute(
            "UPDATE products SET base_price=? WHERE id=?", (price, product_id)
        )
    return price


def sync_to_ontology(
    product_id: str, name: str, brand: str | None, path: str | None = None
) -> bool:
    """Ghi SP mới vào ontology master (data, không phải code core).

    Kernel enrich đọc knowledge/master/products.json (+ brands.json) để
    xác nhận SP hợp lệ. SP thêm từ giao diện chưa có -> ta append entry
    vào cả products.json và brands.json (chỉ thêm data, không sửa logic
    kernel). Trả True nếu đã thêm mới.
    """
    repo_root = Path(__file__).resolve().parent.parent
    master = repo_root / "knowledge" / "master"
    products_path = master / "products.json"
    brands_path = master / "brands.json"  # có thể khác tên; thử brands.json
    if not products_path.exists():
        return False
    try:
        products = json.loads(products_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if any(p.get("id") == product_id for p in products):
        return False
    brand_id = f"BRAND-{product_id}"
    products.append({
        "id": product_id,
        "brand_id": brand_id,
        "name": name,
        "category": "beer",
    })
    products_path.write_text(
        json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Thêm brand nếu file brands tồn tại (để ontology validate qua)
    if brands_path.exists():
        try:
            brands = json.loads(brands_path.read_text(encoding="utf-8"))
            if not any(b.get("id") == brand_id for b in brands):
                brands.append({
                    "id": brand_id,
                    "name": brand or product_id,
                })
                brands_path.write_text(
                    json.dumps(brands, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass
    # Thêm SKU tương ứng (ontology cũng validate skus)
    skus_path = master / "skus.json"
    if skus_path.exists():
        try:
            skus = json.loads(skus_path.read_text(encoding="utf-8"))
            sku_id = f"SKU-{product_id}"
            if not any(s.get("id") == sku_id for s in skus):
                skus.append({
                    "id": sku_id,
                    "product_id": product_id,
                    "pack_size": "330ml",
                    "barcode": f"000{product_id}",
                })
                skus_path.write_text(
                    json.dumps(skus, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass
    return True


def add_product(
    product_id: str,
    name: str,
    brand: str | None,
    source: str,
    base_price: float | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Thêm sản phẩm mới từ giao diện (dynamic). Trả dict sản phẩm."""
    upsert_product(product_id, name, brand, source, base_price=base_price, path=path)
    return get_products(path=path)  # type: ignore[return-value]


def get_products(path: str | None = None) -> list[dict[str, Any]]:
    if path is None:
        path = DEFAULT_DB_PATH
    with _session(path) as c:
        rows = c.execute(
            "SELECT * FROM products ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(
    product_id: str, limit: int = 100, since: str | None = None,
    path: str | None = None,
) -> list[dict[str, Any]]:
    if path is None:
        path = DEFAULT_DB_PATH
    """Lịch sử giá một sản phẩm.

    `since` là ISO timestamp (UTC) — chỉ trả các điểm >= since.
    Dùng cho bộ lọc thời gian trên dashboard (1h/24h/7d).
    """
    with _session(path) as c:
        if since is None:
            rows = c.execute(
                """SELECT * FROM price_points
                   WHERE product_id=? ORDER BY captured_at DESC LIMIT ?""",
                (product_id, limit),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT * FROM price_points
                   WHERE product_id=? AND captured_at >= ?
                   ORDER BY captured_at DESC LIMIT ?""",
                (product_id, since, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def get_history_all(
    since: str | None = None, limit: int = 500, path: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    if path is None:
        path = DEFAULT_DB_PATH
    """Trả lịch sử của TẤT CẢ sản phẩm, nhóm theo product_id.

    Tiện cho vẽ biểu đồ kết hợp trên dashboard.
    """
    with _session(path) as c:
        if since is None:
            rows = c.execute(
                """SELECT * FROM price_points ORDER BY captured_at ASC LIMIT ?""",
                (limit,),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT * FROM price_points WHERE captured_at >= ?
                   ORDER BY captured_at ASC LIMIT ?""",
                (since, limit),
            ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        d = dict(r)
        out.setdefault(d["product_id"], []).append(d)
    return out


def get_latest(path: str | None = None) -> list[dict[str, Any]]:
    if path is None:
        path = DEFAULT_DB_PATH
    """Trả 1 dòng mới nhất của mỗi product, kèm thông tin product."""
    with _session(path) as c:
        rows = c.execute(
            """
            SELECT p.id, p.name, p.brand, p.source,
                   pp.price, pp.currency, pp.captured_at,
                   pp.decision, pp.delta_percent, pp.province
            FROM products p
            LEFT JOIN price_points pp ON pp.product_id = p.id
            WHERE pp.id = (SELECT MAX(id) FROM price_points
                           WHERE product_id = p.id)
               OR pp.id IS NULL
            ORDER BY pp.captured_at DESC NULLS LAST
            """
        ).fetchall()
    return [dict(r) for r in rows]
