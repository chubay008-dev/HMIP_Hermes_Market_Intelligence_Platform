"""db_backend.py — Abstraction layer SQLite ↔ PostgreSQL.

Cho phép db.py và pi_store.py chạy trên cả SQLite (local dev) và PostgreSQL
(Supabase/Render) mà không đổi logic. Chọn backend qua env:

  - DATABASE_URL (hoặc HMIP_DB_PATH cho SQLite)  → DB chính (products, price_points)
  - HMIP_PI_DATABASE_URL (hoặc HMIP_PI_DB_PATH)  → PI DB (observations, events, ...)

Khi *_DATABASE_URL set (postgres://...) → dùng PostgreSQL (psycopg2).
Khi không set → fallback SQLite (giữ hành vi cũ, local dev).

Conversion runtime (SQLite SQL → Postgres-compatible):
  - `?`                → `%s`              (placeholder)
  - `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
  - `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGSERIAL PRIMARY KEY`
  - `PRAGMA ...`       → skip (no-op cho Postgres)

Cursor trả dict cho cả 2 backend (sqlite3.Row / psycopg2 RealDictCursor).
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore
    _HAS_PSYCOPG = True
except ImportError:
    psycopg2 = None  # type: ignore
    RealDictCursor = None  # type: ignore
    _HAS_PSYCOPG = False


def _pg_url(db_path_env: str | None, pg_url_env: str) -> str | None:
    """Trả PostgreSQL URL nếu có, None nếu dùng SQLite."""
    url = os.getenv(pg_url_env, "").strip()
    if url and url.startswith(("postgres://", "postgresql://")):
        return url
    return None


def is_postgres(db_path_env: str | None = None, pg_url_env: str = "DATABASE_URL") -> bool:
    return _pg_url(db_path_env, pg_url_env) is not None


def _adapt_sql(sql: str) -> tuple[str, bool]:
    """Convert SQLite SQL → Postgres-compatible. Trả (sql, is_pg)."""
    # INSERT OR IGNORE INTO → INSERT INTO ... ON CONFLICT DO NOTHING
    # Chỉ khi KHÔNG có mệnh đề ON CONFLICT sẵn trong câu (UPSERT giữ nguyên).
    has_on_conflict = bool(re.search(r"\bON\s+CONFLICT\b", sql, re.IGNORECASE))
    if not has_on_conflict:
        sql = re.sub(
            r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            sql,
            flags=re.IGNORECASE,
        )
        # Nếu là INSERT INTO đơn thuần (từ INSERT OR IGNORE), thêm ON CONFLICT DO NOTHING
        # Detect: INSERT INTO ... VALUES (...) không có ON CONFLICT → thêm suffix
        if re.match(r"\s*INSERT\s+INTO\b", sql, re.IGNORECASE) and not has_on_conflict:
            # Chỉ thêm nếu câu KHÔNG kết thúc bằng RETURNING (đã có)
            if not re.search(r"\bRETURNING\b", sql, re.IGNORECASE):
                sql = sql.rstrip().rstrip(";")
                sql = sql + " ON CONFLICT DO NOTHING"
    # ? → %s
    sql = sql.replace("?", "%s")
    return sql, True


def _adapt_schema_sql(sql: str) -> str:
    """Convert SQLite DDL → Postgres DDL (CREATE TABLE / ALTER TABLE)."""
    sql, _ = _adapt_sql(sql)
    # INTEGER PRIMARY KEY AUTOINCREMENT → BIGSERIAL PRIMARY KEY
    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "BIGSERIAL PRIMARY KEY",
        sql,
        flags=re.IGNORECASE,
    )
    # Bỏ các dòng PRAGMA (không hợp lệ trong Postgres executescript)
    sql = "\n".join(
        line for line in sql.splitlines()
        if not line.strip().upper().startswith("PRAGMA")
    )
    return sql


class _NullCursor:
    """Cursor rỗng cho các lệnh bị skip (PRAGMA trong Postgres)."""

    rowcount = -1
    lastrowid = None

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _PgCursor:
    """Wrap psycopg2 cursor để fetchone/fetchall trả dict + lastrowid hoạt động."""

    def __init__(self, cur):
        self._cur = cur
        self._lastrowid: int | None = None

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid

    def execute(self, sql: str, params: Iterable[Any] = ()) -> "_PgCursor":
        adapted, _ = _adapt_sql(sql)
        # Nếu INSERT cần lastrowid và bảng có SERIAL, dùng RETURNING
        self._cur.execute(adapted, tuple(params))
        return self

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> None:
        adapted, _ = _adapt_sql(sql)
        self._cur.executemany(adapted, list(params))

    def fetchone(self) -> dict[str, Any] | None:
        row = self._cur.fetchone()
        return dict(row) if row else None

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._cur.fetchall()]


class _PgConn:
    """Wrap psycopg2 connection với API tương thích sqlite3."""

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        self._conn.autocommit = False

    def execute(self, sql: str, params: Iterable[Any] = ()) -> _PgCursor:
        # Bỏ qua PRAGMA (không hợp lệ trong Postgres, không cần thiết)
        if sql.strip().upper().startswith("PRAGMA"):
            return _PgCursor(_NullCursor())
        adapted, _ = _adapt_sql(sql)
        cur = self._conn.cursor()
        cur.execute(adapted, tuple(params))
        return _PgCursor(cur)

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> None:
        cur = _PgCursor(self._conn.cursor())
        cur.executemany(sql, params)

    def executescript(self, sql: str) -> None:
        """Postgres: split theo ';' và execute từng statement (DDL)."""
        adapted = _adapt_schema_sql(sql)
        # Postgres không cho forward-reference FK (bảng chưa tạo trong cùng
        # script). Bỏ REFERENCES ở 2 dạng (thứ tự quan trọng: clause riêng
        # trước, inline sau, nếu không inline sẽ ăn mất REFERENCES của clause
        # và để lại FOREIGN KEY rỗng):
        #  (b) clause riêng:    `, FOREIGN KEY (col) REFERENCES tbl(col)`
        #      → bỏ cả comma + clause (tránh trailing comma / FK rỗng)
        #  (a) inline column:  `col TEXT REFERENCES pi_brands(brand_id)`
        #      → bỏ "REFERENCES ..." giữ lại `col TEXT`
        # Integrity check làm ở app layer (đã có trước đó cho SQLite).
        adapted = re.sub(
            r",\s*FOREIGN KEY\s*\([^)]*\)\s+REFERENCES\s+\w+\([^)]*\)",
            "",
            adapted,
            flags=re.IGNORECASE,
        )
        adapted = re.sub(r"\s+REFERENCES\s+\w+\([^)]*\)", "", adapted, flags=re.IGNORECASE)
        cur = self._conn.cursor()
        # Split đơn giản theo ';' — đủ cho CREATE TABLE / CREATE INDEX
        for stmt in adapted.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, _val):
        pass  # RealDictCursor đã trả dict

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def table_columns(self, table: str) -> set[str]:
        """Danh sách cột của bảng (dùng cho migration check)."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            (table,),
        )
        # RealDictCursor trả dict-like; lấy giá trị đầu tiên của mỗi row
        return {list(r.values())[0] for r in cur.fetchall()}

    def add_column(self, table: str, col_def: str) -> None:
        cur = self._conn.cursor()
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


class _SqliteConn:
    """Wrap sqlite3 connection — passthrough (giữ hành vi gốc)."""

    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql: str, params: Iterable[Any] = ()):
        return self._conn.execute(sql, tuple(params))

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]):
        return self._conn.executemany(sql, list(params))

    def executescript(self, sql: str):
        # Bỏ PRAGMA không cần (foreign_keys đã set ở __init__)
        return self._conn.executescript(sql)

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, val):
        self._conn.row_factory = val

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def table_columns(self, table: str) -> set[str]:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r["name"] for r in rows}

    def add_column(self, table: str, col_def: str) -> None:
        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def connect(
    sqlite_path: str,
    pg_url_env: str = "DATABASE_URL",
) -> _SqliteConn | _PgConn:
    """Trả connection phù hợp. Nếu *_DATABASE_URL set → Postgres, else SQLite."""
    dsn = _pg_url(sqlite_path, pg_url_env)
    if dsn:
        if not _HAS_PSYCOPG:
            raise RuntimeError(
                "DATABASE_URL set (PostgreSQL) nhưng psycopg2 chưa cài. "
                "Chạy: pip install psycopg2-binary"
            )
        return _PgConn(dsn)
    return _SqliteConn(sqlite_path)


@contextmanager
def session(
    sqlite_path: str,
    pg_url_env: str = "DATABASE_URL",
):
    """Context manager session — commit tự động, close luôn."""
    conn = connect(sqlite_path, pg_url_env)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
