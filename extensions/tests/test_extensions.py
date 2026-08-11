"""Test cho tầng extensions (adapter thật, DB, workflow runner, API).

Chạy: /tmp/hmip-venv/bin/python -m pytest extensions/tests -q
"""

from __future__ import annotations

import os
import tempfile

import pytest

from extensions import db
from extensions.collect_adapters import SimulatedPriceAdapter
from extensions.run_workflow import resolve_base_price, run_prc_001
from core.exceptions import WorkflowExecutionException


@pytest.fixture()
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", path)
    monkeypatch.setenv("HMIP_DB_PATH", path)
    db.init_db(path)
    yield path
    os.unlink(path)


# ----------------------------------------------------- collect adapter

def test_simulated_adapter_returns_known_product():
    out = SimulatedPriceAdapter().fetch({"product_id": "P123", "source": "demo"})
    assert out["product_id"] == "P123"
    assert out["brand"] == "Saigon Beer"
    assert "price_text" in out
    assert out["currency"] == "VND"


def test_simulated_adapter_accepts_unknown_product_with_default_price():
    # SP mới (thêm từ giao diện) không có trong catalog cứng -> adapter
    # vẫn sinh giá mô phỏng quanh mức mặc định để demo được.
    out = SimulatedPriceAdapter().fetch(
        {"product_id": "NOPE", "source": "demo", "product_name": "Mới", "brand": "B"}
    )
    assert out["product_id"] == "NOPE"
    price = float(out["price_text"].replace(",", ""))
    assert 18000 * 0.88 <= price <= 18000 * 1.12


def test_simulated_price_stays_within_volatility_band():
    adapter = SimulatedPriceAdapter(volatility=0.10)
    for _ in range(50):
        out = adapter.fetch({"product_id": "P123", "source": "t"})
        price = float(out["price_text"].replace(",", ""))
        assert 18000 * 0.90 <= price <= 18000 * 1.10


def test_adapter_health():
    assert SimulatedPriceAdapter().health() is True


# ------------------------------------------------------------ base price

def test_base_price_from_catalog():
    assert resolve_base_price("P123") == 18000.0
    assert resolve_base_price("P456") == 22000.0


def test_base_price_env_override(monkeypatch, temp_db):
    monkeypatch.setenv("HMIP_BASE_PRICE_P123", "25000")
    assert resolve_base_price("P123") == 25000.0


def test_base_price_fallback_for_unknown_is_none(temp_db):
    # SP chưa có mốc -> None (sẽ tự động gán = giá quét đầu)
    assert resolve_base_price("UNKNOWN-XYZ") is None


# -------------------------------------------------------------------- db

def test_db_roundtrip(temp_db):
    db.upsert_product("P123", "Saigon Special 330ml", "Saigon Beer", "demo", temp_db)
    db.record_price_point("P123", 18500.0, "VND", "ALERT", 2.78, "demo://x", temp_db)

    products = db.get_products(temp_db)
    assert len(products) >= 1
    assert products[0]["name"] == "Saigon Special 330ml"

    history = db.get_history("P123", path=temp_db)
    assert len(history) == 1
    assert history[0]["decision"] == "ALERT"
    assert history[0]["price"] == 18500.0


def test_db_upsert_is_idempotent(temp_db):
    for _ in range(3):
        db.upsert_product("P123", "Tên mới", "Saigon Beer", "demo", temp_db)
    assert len(db.get_products(temp_db)) == 1
    assert db.get_products(temp_db)[0]["name"] == "Tên mới"


def test_db_latest_returns_most_recent_per_product(temp_db):
    db.upsert_product("P123", "A", "B", "demo", temp_db)
    db.record_price_point("P123", 100.0, "VND", "IGNORE", 0.0, None, temp_db)
    db.record_price_point("P123", 200.0, "VND", "ALERT", 5.5, None, temp_db)
    latest = db.get_latest(temp_db)
    assert len(latest) == 1
    assert latest[0]["price"] == 200.0


# -------------------------------------------------------- workflow runner

def test_run_prc_001_completes_and_persists(temp_db):
    result = run_prc_001("P123", source="test")
    assert result["status"] == "COMPLETED"
    assert result["saved"] is True
    # cả 7 task đều để lại output trong lineage
    for task in ("collect", "extract", "validate", "enrich", "compare", "decide", "alert"):
        assert task in result["steps"], f"thiếu output của task '{task}'"


def test_run_prc_001_decision_matches_thresholds(temp_db):
    """Quyết định phải nhất quán với delta% do compare tính ra."""
    result = run_prc_001("P123", source="test")
    delta = abs(result["steps"]["compare"]["delta_percent"])
    decision = result["steps"]["decide"]["decision"]
    if delta >= 10:
        assert decision == "ESCALATE"
    elif delta >= 5:
        assert decision == "ALERT"
    else:
        assert decision == "IGNORE"


def test_run_prc_001_unknown_product_fails_with_compensation(temp_db):
    result = run_prc_001("P999", source="test")
    assert result["status"] == "FAILED"
    assert result["saved"] is False
    assert result["compensation"]["triggered"] is True
    assert result["compensation"]["completed"] is True


def test_run_prc_001_no_save_flag(temp_db):
    result = run_prc_001("P123", source="test", persist=False)
    assert result["status"] == "COMPLETED"
    assert result["saved"] is False


# --------------------------------------------------------------- web API

def test_api_endpoints(temp_db, monkeypatch):
    monkeypatch.delenv("HMIP_API_TOKEN", raising=False)
    from fastapi.testclient import TestClient
    from extensions.api import app

    client = TestClient(app)

    assert client.get("/api/health").json()["status"] == "ok"

    catalog = client.get("/api/catalog").json()
    assert {c["product_id"] for c in catalog} == set(
        ["P123", "P456"] + list(__import__("extensions.default_products", fromlist=["DEFAULT_PRODUCTS"]).DEFAULT_PRODUCTS.keys())
    )

    run = client.post("/api/run", json={"product_id": "P123", "source": "api-test"})
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "COMPLETED"
    assert body["decision"] in {"IGNORE", "ALERT", "ESCALATE", "HUMAN_REVIEW"}

    assert len(client.get("/api/latest").json()) >= 1
    assert client.get("/api/history/P123").status_code == 200
    assert client.get("/api/history/KHONG-CO").status_code == 404


def test_api_run_unknown_product_still_executes(temp_db, monkeypatch):
    # Kịch bản thực tế: thêm SP mới qua /api/products (sync ontology) rồi /api/run
    monkeypatch.delenv("HMIP_API_TOKEN", raising=False)
    from fastapi.testclient import TestClient
    from extensions.api import app

    client = TestClient(app)
    add = client.post("/api/products", json={"product_id": "P999", "name": "Tmp", "brand": "B"})
    assert add.status_code == 200
    resp = client.post("/api/run", json={"product_id": "P999"})
    assert resp.status_code == 200
    assert resp.json()["status"] in {"COMPLETED", "FAILED"}
    # cleanup ontology
    import json as _j, pathlib
    master = pathlib.Path(__file__).resolve().parents[2] / "knowledge" / "master"
    for fn in ("products", "brands", "skus"):
        fp = master / f"{fn}.json"
        d = _j.loads(fp.read_text())
        d = [x for x in d if x.get("id") != "P999" and x.get("product_id") != "P999"
             and x.get("brand_id") != "BRAND-P999"]
        fp.write_text(_j.dumps(d, ensure_ascii=False, indent=2))
