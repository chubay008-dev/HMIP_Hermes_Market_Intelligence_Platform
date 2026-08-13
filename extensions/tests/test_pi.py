"""test_pi.py — Kiểm thử package extensions.pi (Price Intelligence).

Chạy độc lập với core/domains. Dùng temp DB, seed nhẹ (history_days=20
để có ít nhất 1 price event từ jump).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from extensions.pi import ai_analyst, analytics, events, normalization, pi_store, seed

PI_DB = str(Path(tempfile.gettempdir()) / "hmip_pi_test_suite.db")


@pytest.fixture(scope="module")
def db():
    if Path(PI_DB).exists():
        Path(PI_DB).unlink()
    res = seed.seed_full(history_days=20, path=PI_DB, seed=42)
    assert res["products"] == 68
    assert res["observations"] > 0
    return PI_DB


def test_schema_init():
    p = str(Path(tempfile.gettempdir()) / "hmip_pi_schema.db")
    if Path(p).exists():
        Path(p).unlink()
    pi_store.init_pi_db(p)
    for t in ("pi_observations", "pi_price_events", "pi_alerts",
              "pi_promotions", "pi_products", "pi_skus", "pi_brands"):
        row = pi_store.fetch_one(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,), path=p)
        assert row, f"missing table {t}"


def test_normalization():
    n = normalization.normalize_price(
        regular_price=240000, pack_quantity=24, unit_volume_ml=330,
        promotion_price=200000, effective_price=200000)
    # 200000 / (24*330ml=7920ml) * 100 = 2525.25
    assert 2500 < n.price_per_100ml < 2550
    assert n.price_per_unit == pytest.approx(200000 / 24, rel=1e-3)


def test_seed_counts(db):
    k = analytics.kpi_overview(path=db)
    assert k["observation_count"] > 0
    assert k["avg_price"] > 0
    assert k["price_index"] > 0


def test_channel_comparison(db):
    ch = analytics.channel_comparison(path=db)
    assert len(ch["channels"]) == 18
    assert ch["lowest_channel"]["channel_id"] == "SHOPEE"
    assert ch["highest_channel"]["channel_id"] == "WINMART"


def test_regional_pricing(db):
    reg = analytics.regional_pricing(path=db)
    assert len(reg["regions"]) == 5


def test_price_index_by_brand(db):
    idx = analytics.price_index_by_brand(path=db)
    assert len(idx["brands"]) > 0
    assert idx["cheapest_brand"] is not None
    assert idx["most_expensive_brand"] is not None


def test_competitor_comparison(db):
    comp = analytics.competitor_comparison(filters={"product_id": "P123"}, path=db)
    assert comp["comparable_universe"] is not None
    assert isinstance(comp["rows"], list)


def test_promotion_intelligence(db):
    promo = analytics.promotion_intelligence(path=db)
    assert promo["total_promotions"] > 0
    assert 5 < promo["avg_discount_pct"] < 20
    assert "Flash Sale" in promo["promotion_by_type"]


def test_events_and_alerts(db):
    evs = events.list_events(limit=10, path=db)
    assert len(evs) > 0
    for e in evs:
        assert e["event_type"] in ("PRICE_INCREASE", "PRICE_DECREASE")
        assert abs(e["change_percent"]) >= 5
    als = events.list_alerts(path=db)
    for a in als:
        assert a["severity"] == "CRITICAL"


def test_ai_event_analysis(db):
    evs = events.list_events(limit=1, path=db)
    ai = ai_analyst.analyze_event(evs[0]["event_id"], path=db)
    assert ai["model"]
    assert ai["fact"]
    assert ai["confidence"] > 0
    assert ai["recommendation"]
    logged = ai_analyst.list_analyses(path=db)
    assert len(logged) >= 1


def test_ai_question(db):
    ans = ai_analyst.ask_question("Sản phẩm nào đang có promotion sâu nhất?", path=db)
    assert ans["answer"]
    assert ans["model"]
    assert ans["confidence"] > 0


def test_collector_tiki_real(db, monkeypatch):
    """Hướng A+C: collector Tiki parse + lưu đúng chuẩn (offline mock).

    Test offline: mock Tiki search trả JSON mẫu để không phụ thuộc mạng/
    rate-limit Tiki. Test gọi mạng thật nằm ở test_collector_tiki_live (skip).
    """
    import tempfile, os
    from extensions.pi import collectors as col, analytics as an

    fake_item = {
        "name": "Bia Heineken Lager (330ml / Lon) thùng 24 lon",
        "price": 598800,
        "list_price": 650000,
    }

    class FakeTiki(col.TikiCollector):
        def search(self, query, limit=10):
            return [fake_item]

    col.COLLECTORS["TIKI"] = FakeTiki

    tdb = tempfile.mktemp(suffix=".db")
    pp = col.collect_product("TIKI", "P456", "Heineken Lager 330ml")
    assert pp is not None, "phải parse được item Tiki"
    assert pp.regular_price == 598800
    assert pp.promotion_price == 650000  # list > price -> promo
    col.store_price_point(pp, today="2026-08-12", path=tdb)
    obs = pi_store.fetch_all("SELECT source, normalized_price FROM pi_observations", path=tdb)
    assert obs and obs[0]["source"] == "tiki"
    # chuẩn hóa ra số dương hợp lý (598800/24lon/330ml -> ~756/100ml; promo 650k -> ~8212)
    assert obs[0]["normalized_price"] > 0
    k = an.kpi_overview(path=tdb)
    assert k["observation_count"] >= 1
    try:
        col.collect_product("SHOPEE", "P456", "Heineken Lager 330ml")
        assert False, "Shopee phải raise NotImplementedError"
    except NotImplementedError:
        pass
    os.remove(tdb)


@pytest.mark.skip(reason="needs live Tiki (rate-limited); run manually")
def test_collector_tiki_live():
    from extensions.pi import collectors as col
    pp = col.collect_product("TIKI", "P456", "Heineken Lager 330ml")
    assert pp and pp.regular_price > 0
