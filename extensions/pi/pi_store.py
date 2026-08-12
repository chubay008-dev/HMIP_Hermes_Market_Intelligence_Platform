"""pi_store.py — SQLite persistence layer cho HMIP Price Intelligence (PI).

Đây là tầng lưu trữ ĐỘC LẬP với core kernel gốc (core/, domains/).
Mọi bảng PI sống trong file DB riêng (HMIP_PI_DB_PATH, mặc định
hmip_pi.db) để không phá ranh giới "core không phụ thuộc domain" và
không làm hỏng DB giám sát giá cũ.

Schema tuân thủ:
  * Core Data Model (Spec §13)            — Product/SKU/Seller/Channel/Region/
                                            Observation/Promotion/Event
  * Canonical Data Contract (§41)        — PriceObservation đẩy đủ trường
  * Domain Boundaries (§63)               — Catalog / Market / Price /
                                            Promotion / Intelligence / AI
  * Provenance (§8) + Time Model (§44)    — source/source_url/confidence +
                                            observed_at/collected_at
  * Normalization (§11)                   — unit_price / normalized_price
                                            (giá quy về 100ml để so sánh)

Tất cả migration đều an toàn (CREATE TABLE IF NOT EXISTS + ALTER cột
có bắt lỗi OperationalError).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

DEFAULT_PI_DB_PATH = os.getenv("HMIP_PI_DB_PATH", "hmip_pi.db")


def _connect(path: str = DEFAULT_PI_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_pi_db(path: str | None = None) -> None:
    if path is None:
        path = DEFAULT_PI_DB_PATH
    conn = _connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pi_brands (
                brand_id   TEXT PRIMARY KEY,
                name       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pi_categories (
                category_id TEXT PRIMARY KEY,
                name        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pi_products (
                product_id   TEXT PRIMARY KEY,
                brand_id     TEXT REFERENCES pi_brands(brand_id),
                category_id  TEXT REFERENCES pi_categories(category_id),
                product_name TEXT NOT NULL,
                variant      TEXT,
                pack_size    TEXT,
                volume_ml    REAL,
                unit         TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_skus (
                sku_id          TEXT PRIMARY KEY,
                product_id      TEXT REFERENCES pi_products(product_id),
                barcode         TEXT,
                pack_quantity   REAL,
                unit_volume_ml  REAL,
                normalized_unit TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_channels (
                channel_id   TEXT PRIMARY KEY,
                channel_name TEXT NOT NULL,
                channel_type TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_regions (
                region_id TEXT PRIMARY KEY,
                country  TEXT,
                region   TEXT,
                province TEXT,
                city     TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_sellers (
                seller_id           TEXT PRIMARY KEY,
                seller_name         TEXT NOT NULL,
                seller_type         TEXT,
                verification_status TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_observations (
                observation_id  TEXT PRIMARY KEY,
                sku_id          TEXT REFERENCES pi_skus(sku_id),
                product_id      TEXT REFERENCES pi_products(product_id),
                brand_id        TEXT REFERENCES pi_brands(brand_id),
                channel_id      TEXT REFERENCES pi_channels(channel_id),
                seller_id       TEXT REFERENCES pi_sellers(seller_id),
                region_id       TEXT REFERENCES pi_regions(region_id),
                observed_at     TEXT NOT NULL,
                collected_at    TEXT NOT NULL,
                regular_price   REAL NOT NULL,
                promotion_price REAL,
                effective_price REAL NOT NULL,
                currency        TEXT,
                unit_price      REAL,
                normalized_price REAL,
                availability    TEXT,
                source          TEXT,
                source_url      TEXT,
                extraction_method TEXT,
                confidence      REAL,
                metadata        TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_promotions (
                promotion_id     TEXT PRIMARY KEY,
                sku_id           TEXT REFERENCES pi_skus(sku_id),
                channel_id       TEXT REFERENCES pi_channels(channel_id),
                seller_id        TEXT REFERENCES pi_sellers(seller_id),
                region_id        TEXT REFERENCES pi_regions(region_id),
                start_time       TEXT,
                end_time         TEXT,
                regular_price    REAL,
                promotion_price  REAL,
                discount_percent REAL,
                promotion_type   TEXT,
                campaign         TEXT,
                source_url       TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_price_events (
                event_id       TEXT PRIMARY KEY,
                sku_id         TEXT REFERENCES pi_skus(sku_id),
                channel_id     TEXT,
                region_id      TEXT,
                timestamp      TEXT NOT NULL,
                old_price      REAL,
                new_price      REAL,
                change_percent REAL,
                event_type     TEXT,
                significance   TEXT,
                confidence     REAL,
                dedup_key      TEXT
            );

            CREATE TABLE IF NOT EXISTS pi_alerts (
                alert_id    TEXT PRIMARY KEY,
                event_id    TEXT REFERENCES pi_price_events(event_id),
                sku_id      TEXT,
                severity    TEXT,
                created_at  TEXT NOT NULL,
                message     TEXT,
                dedup_key   TEXT,
                acknowledged INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS pi_ai_analyses (
                analysis_id     TEXT PRIMARY KEY,
                event_id        TEXT,
                question        TEXT,
                fact            TEXT,
                evidence        TEXT,
                inference       TEXT,
                confidence      REAL,
                recommendation  TEXT,
                model           TEXT,
                prompt_version  TEXT,
                generated_at    TEXT NOT NULL,
                input_event_ids TEXT,
                evidence_ids    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_pi_obs_sku        ON pi_observations(sku_id);
            CREATE INDEX IF NOT EXISTS idx_pi_obs_product   ON pi_observations(product_id);
            CREATE INDEX IF NOT EXISTS idx_pi_obs_channel   ON pi_observations(channel_id);
            CREATE INDEX IF NOT EXISTS idx_pi_obs_region    ON pi_observations(region_id);
            CREATE INDEX IF NOT EXISTS idx_pi_obs_time      ON pi_observations(observed_at);
            CREATE INDEX IF NOT EXISTS idx_pi_evt_sku       ON pi_price_events(sku_id);
            CREATE INDEX IF NOT EXISTS idx_pi_evt_time      ON pi_price_events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_pi_alert_sev     ON pi_alerts(severity);
            CREATE INDEX IF NOT EXISTS idx_pi_promo_sku     ON pi_promotions(sku_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def bulk_insert_events(rows: list[dict[str, Any]], path: str | None = None) -> int:
    cols = ["event_id", "sku_id", "channel_id", "region_id", "timestamp",
            "old_price", "new_price", "change_percent", "event_type",
            "significance", "confidence", "dedup_key"]
    _bulk("pi_price_events", cols, rows, path)
    return len(rows)


def bulk_insert_alerts(rows: list[dict[str, Any]], path: str | None = None) -> int:
    cols = ["alert_id", "event_id", "sku_id", "severity", "created_at",
            "message", "dedup_key"]
    _bulk("pi_alerts", cols, rows, path)
    return len(rows)


def _bulk(table: str, cols: list[str], rows: list[dict[str, Any]],
          path: str | None = None) -> None:
    if not rows:
        return
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    sql = f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})"
    with _session(path) as c:
        c.executemany(sql, [[r.get(col) for col in cols] for r in rows])


@contextmanager
def _session(path: str | None = None):
    conn = _connect(path or DEFAULT_PI_DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Generic upserts (idempotent)
# ---------------------------------------------------------------------------

def upsert_brand(brand_id: str, name: str, path: str | None = None) -> None:
    with _session(path) as c:
        c.execute(
            "INSERT INTO pi_brands (brand_id, name) VALUES (?, ?) "
            "ON CONFLICT(brand_id) DO UPDATE SET name=excluded.name",
            (brand_id, name),
        )


def upsert_category(category_id: str, name: str, path: str | None = None) -> None:
    with _session(path) as c:
        c.execute(
            "INSERT INTO pi_categories (category_id, name) VALUES (?, ?) "
            "ON CONFLICT(category_id) DO UPDATE SET name=excluded.name",
            (category_id, name),
        )


def upsert_channel(channel_id: str, channel_name: str, channel_type: str | None = None,
                   path: str | None = None) -> None:
    with _session(path) as c:
        c.execute(
            "INSERT INTO pi_channels (channel_id, channel_name, channel_type) VALUES (?, ?, ?) "
            "ON CONFLICT(channel_id) DO UPDATE SET channel_name=excluded.channel_name, "
            "channel_type=excluded.channel_type",
            (channel_id, channel_name, channel_type),
        )


def upsert_region(region_id: str, country: str, region: str, province: str,
                  city: str | None = None, path: str | None = None) -> None:
    with _session(path) as c:
        c.execute(
            "INSERT INTO pi_regions (region_id, country, region, province, city) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(region_id) DO UPDATE SET country=excluded.country, "
            "region=excluded.region, province=excluded.province, city=excluded.city",
            (region_id, country, region, province, city),
        )


def upsert_seller(seller_id: str, seller_name: str, seller_type: str | None = None,
                  verification_status: str | None = None, path: str | None = None) -> None:
    with _session(path) as c:
        c.execute(
            "INSERT INTO pi_sellers (seller_id, seller_name, seller_type, verification_status) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(seller_id) DO UPDATE SET seller_name=excluded.seller_name, "
            "seller_type=excluded.seller_type, verification_status=excluded.verification_status",
            (seller_id, seller_name, seller_type, verification_status),
        )


def upsert_product(product_id: str, brand_id: str, category_id: str, product_name: str,
                   variant: str | None = None, pack_size: str | None = None,
                   volume_ml: float | None = None, unit: str | None = None,
                   path: str | None = None) -> None:
    with _session(path) as c:
        c.execute(
            "INSERT INTO pi_products (product_id, brand_id, category_id, product_name, "
            "variant, pack_size, volume_ml, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(product_id) DO UPDATE SET brand_id=excluded.brand_id, "
            "category_id=excluded.category_id, product_name=excluded.product_name, "
            "variant=excluded.variant, pack_size=excluded.pack_size, "
            "volume_ml=excluded.volume_ml, unit=excluded.unit",
            (product_id, brand_id, category_id, product_name, variant, pack_size,
             volume_ml, unit),
        )


def upsert_sku(sku_id: str, product_id: str, barcode: str | None = None,
               pack_quantity: float | None = None, unit_volume_ml: float | None = None,
               normalized_unit: str | None = None, path: str | None = None) -> None:
    with _session(path) as c:
        c.execute(
            "INSERT INTO pi_skus (sku_id, product_id, barcode, pack_quantity, "
            "unit_volume_ml, normalized_unit) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(sku_id) DO UPDATE SET product_id=excluded.product_id, "
            "barcode=excluded.barcode, pack_quantity=excluded.pack_quantity, "
            "unit_volume_ml=excluded.unit_volume_ml, normalized_unit=excluded.normalized_unit",
            (sku_id, product_id, barcode, pack_quantity, unit_volume_ml, normalized_unit),
        )


def bulk_insert_observations(rows: list[dict[str, Any]], path: str | None = None) -> int:
    """Batch insert observations (1 session, executemany). Rất nhanh cho
    seed hàng chục nghìn dòng. Mỗi row là dict có các khoá của insert_observation."""
    if not rows:
        return 0
    cols = [
        "observation_id", "sku_id", "product_id", "brand_id", "channel_id",
        "seller_id", "region_id", "observed_at", "collected_at", "regular_price",
        "promotion_price", "effective_price", "currency", "unit_price",
        "normalized_price", "availability", "source", "source_url",
        "extraction_method", "confidence", "metadata",
    ]
    with _session(path) as c:
        c.executemany(
            f"""INSERT OR IGNORE INTO pi_observations
               ({', '.join(cols)})
               VALUES ({', '.join('?' for _ in cols)})""",
            [tuple(r.get(col) for col in cols) for r in rows],
        )
    return len(rows)


def bulk_insert_promotions(rows: list[dict[str, Any]], path: str | None = None) -> int:
    if not rows:
        return 0
    cols = [
        "promotion_id", "sku_id", "channel_id", "seller_id", "region_id",
        "start_time", "end_time", "regular_price", "promotion_price",
        "discount_percent", "promotion_type", "campaign", "source_url",
    ]
    with _session(path) as c:
        c.executemany(
            f"""INSERT OR IGNORE INTO pi_promotions
               ({', '.join(cols)})
               VALUES ({', '.join('?' for _ in cols)})""",
            [tuple(r.get(col) for col in cols) for r in rows],
        )
    return len(rows)


def insert_observation(
    observation_id: str, sku_id: str, product_id: str, brand_id: str,
    channel_id: str, seller_id: str, region_id: str, observed_at: str,
    collected_at: str, regular_price: float, effective_price: float,
    currency: str = "VND", promotion_price: float | None = None,
    unit_price: float | None = None, normalized_price: float | None = None,
    availability: str | None = "in_stock", source: str | None = None,
    source_url: str | None = None, extraction_method: str | None = None,
    confidence: float | None = 0.9, metadata: str | None = None,
    path: str | None = None,
) -> None:
    with _session(path) as c:
        c.execute(
            """INSERT OR IGNORE INTO pi_observations
               (observation_id, sku_id, product_id, brand_id, channel_id, seller_id,
                region_id, observed_at, collected_at, regular_price, promotion_price,
                effective_price, currency, unit_price, normalized_price, availability,
                source, source_url, extraction_method, confidence, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (observation_id, sku_id, product_id, brand_id, channel_id, seller_id,
             region_id, observed_at, collected_at, regular_price, promotion_price,
             effective_price, currency, unit_price, normalized_price, availability,
             source, source_url, extraction_method, confidence, metadata),
        )


def insert_promotion(
    promotion_id: str, sku_id: str, channel_id: str | None, seller_id: str | None,
    region_id: str | None, start_time: str | None, end_time: str | None,
    regular_price: float | None, promotion_price: float | None,
    discount_percent: float | None, promotion_type: str | None = None,
    campaign: str | None = None, source_url: str | None = None,
    path: str | None = None,
) -> None:
    with _session(path) as c:
        c.execute(
            """INSERT OR IGNORE INTO pi_promotions
               (promotion_id, sku_id, channel_id, seller_id, region_id, start_time,
                end_time, regular_price, promotion_price, discount_percent,
                promotion_type, campaign, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (promotion_id, sku_id, channel_id, seller_id, region_id, start_time,
             end_time, regular_price, promotion_price, discount_percent,
             promotion_type, campaign, source_url),
        )


def insert_event(
    event_id: str, sku_id: str, channel_id: str | None, region_id: str | None,
    timestamp: str, old_price: float | None, new_price: float | None,
    change_percent: float | None, event_type: str, significance: str,
    confidence: float, dedup_key: str | None = None, path: str | None = None,
) -> bool:
    """Trả True nếu thực sự chèn mới (chưa tồn tại), False nếu IGNORE do trùng PK."""
    with _session(path) as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO pi_price_events
               (event_id, sku_id, channel_id, region_id, timestamp, old_price,
                new_price, change_percent, event_type, significance, confidence, dedup_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, sku_id, channel_id, region_id, timestamp, old_price,
             new_price, change_percent, event_type, significance, confidence, dedup_key),
        )
        return cur.rowcount > 0


def insert_alert(
    alert_id: str, event_id: str | None, sku_id: str | None, severity: str,
    created_at: str, message: str, dedup_key: str | None = None,
    path: str | None = None,
) -> bool:
    with _session(path) as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO pi_alerts
               (alert_id, event_id, sku_id, severity, created_at, message, dedup_key)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (alert_id, event_id, sku_id, severity, created_at, message, dedup_key),
        )
        return cur.rowcount > 0


def insert_ai_analysis(
    analysis_id: str, event_id: str | None, question: str | None,
    fact: str, evidence: str, inference: str, confidence: float,
    recommendation: str, model: str, prompt_version: str, generated_at: str,
    input_event_ids: str | None = None, evidence_ids: str | None = None,
    path: str | None = None,
) -> None:
    with _session(path) as c:
        c.execute(
            """INSERT OR IGNORE INTO pi_ai_analyses
               (analysis_id, event_id, question, fact, evidence, inference, confidence,
                recommendation, model, prompt_version, generated_at, input_event_ids,
                evidence_ids)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (analysis_id, event_id, question, fact, evidence, inference, confidence,
             recommendation, model, prompt_version, generated_at, input_event_ids,
             evidence_ids),
        )


# ---------------------------------------------------------------------------
# Queries used by analytics / API
# ---------------------------------------------------------------------------

def fetch_all(query: str, params: Iterable[Any] = (), path: str | None = None) -> list[dict[str, Any]]:
    if path is None:
        path = DEFAULT_PI_DB_PATH
    with _session(path) as c:
        rows = c.execute(query, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def fetch_one(query: str, params: Iterable[Any] = (), path: str | None = None) -> dict[str, Any] | None:
    if path is None:
        path = DEFAULT_PI_DB_PATH
    with _session(path) as c:
        row = c.execute(query, tuple(params)).fetchone()
    return dict(row) if row else None


def count_rows(table: str, path: str | None = None) -> int:
    if path is None:
        path = DEFAULT_PI_DB_PATH
    with _session(path) as c:
        row = c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])


def db_path_resolved(path: str | None = None) -> str:
    return path or DEFAULT_PI_DB_PATH


def clear_observations(path: str | None = None) -> int:
    """Xóa sạch observation + event + alert (demo/thật) — giữ catalog/schema.

    Trả số dòng đã xóa. Dùng trước khi nạp data thật 100%.
    """
    if path is None:
        path = DEFAULT_PI_DB_PATH
    total = 0
    with _session(path) as c:
        for tbl in ("pi_alerts", "pi_events", "pi_observations"):
            cur = c.execute(f"DELETE FROM {tbl}").rowcount
            total += cur or 0
    return total
