"""Test cho biểu đồ (chart) endpoint và lọc thời gian DB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from extensions import db


@pytest.fixture()
def seeded_db(tmp_path):
    p = str(tmp_path / "chart.db")
    db.init_db(path=p)
    now = datetime.now(timezone.utc)
    db.upsert_product("P123", "Saigon", "Saigon Beer", "demo", path=p)
    # seed thủ công với captured_at khác nhau
    import sqlite3
    rows = [
        ("P123", 17000, "VND", -5.5, "ALERT", (now - timedelta(minutes=120)).isoformat()),
        ("P123", 18500, "VND", 2.7, "IGNORE", (now - timedelta(minutes=30)).isoformat()),
        ("P123", 18100, "VND", 0.5, "IGNORE", (now - timedelta(minutes=1)).isoformat()),
    ]
    c = sqlite3.connect(p)
    c.executemany(
        "INSERT INTO price_points (product_id,price,currency,delta_percent,decision,captured_at) VALUES (?,?,?,?,?,?)",
        rows,
    )
    c.commit(); c.close()
    db.upsert_product("P456", "Heineken", "Heineken", "demo", path=p)
    c = sqlite3.connect(p)
    c.execute(
        "INSERT INTO price_points (product_id,price,currency,delta_percent,decision,captured_at) VALUES (?,?,?,?,?,?)",
        ("P456", 23000, "VND", 4.5, "IGNORE", (now - timedelta(minutes=61)).isoformat()),
    )
    c.commit(); c.close()
    return p


def test_get_history_since_filter(seeded_db):
    p = seeded_db
    since = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    rows = db.get_history("P123", since=since, path=p)
    assert len(rows) == 2
    assert all(r["price"] in (18500, 18100) for r in rows)


def test_get_history_all_groups_by_product(seeded_db):
    p = seeded_db
    out = db.get_history_all(path=p)
    assert set(out.keys()) == {"P123", "P456"}
    assert len(out["P123"]) == 3
    assert len(out["P456"]) == 1


def test_get_history_all_since(seeded_db):
    p = seeded_db
    since = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    out = db.get_history_all(since=since, path=p)
    assert len(out.get("P123", [])) == 2
    assert "P456" not in out


def test_chart_endpoint_filters_by_range(seeded_db, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr("extensions.db.DEFAULT_DB_PATH", seeded_db)
    from extensions.api import app

    client = TestClient(app)
    r = client.get("/api/chart?range=all")
    assert r.status_code == 200
    body = r.json()
    assert "P123" in body["products"] and "P456" in body["products"]
    assert len(body["products"]["P123"]["points"]) == 3
    r1 = client.get("/api/chart?range=1h")
    assert r1.status_code == 200
    assert len(r1.json()["products"]["P123"]["points"]) == 2
    assert "P456" not in r1.json()["products"]
