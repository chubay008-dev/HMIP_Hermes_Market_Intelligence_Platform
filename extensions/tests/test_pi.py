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
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,), path=p)
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


def test_price_trend_channel_breakdown(db):
    """price_trend series 'channel_breakdown' → multi-line per kênh."""
    t = analytics.price_trend({}, series=["market_avg", "channel_breakdown"], path=db)
    cb = t["series"].get("channel_breakdown", {})
    assert len(cb) == 18, f"expected 18 channels, got {len(cb)}"
    # Mỗi kênh là list [{t,v}] — giá TB theo ngày
    for name, arr in list(cb.items())[:3]:
        assert isinstance(arr, list) and arr
        assert all("t" in p and "v" in p for p in arr), f"bad shape for {name}"
        assert all(p["v"] > 0 for p in arr), f"non-positive price for {name}"
    # Tên hiển thị (channel_name) thay vì channel_id thô
    assert "Shopee" in cb or "TIKI" in cb or any("Shop" in n for n in cb)


def test_price_trend_channel_breakdown_with_product_filter(db):
    """Filter theo product → channel_breakdown chỉ cho SP đó."""
    t = analytics.price_trend({"product_id": "P123"},
                              series=["sku_price", "channel_breakdown"], path=db)
    cb = t["series"].get("channel_breakdown", {})
    assert len(cb) > 0
    assert t["series"]["sku_price"]  # series chính vẫn có


def test_promotion_intelligence_by_channel(db):
    """promotion_by_channel → so sánh độ sâu KM cross-channel."""
    promo = analytics.promotion_intelligence(path=db)
    bc = promo.get("promotion_by_channel", [])
    assert len(bc) == 18, f"expected 18 channels, got {len(bc)}"
    assert all("channel" in c and "avg_discount_pct" in c for c in bc)
    assert all(0 <= c["avg_discount_pct"] <= 100 for c in bc)
    # Sắp xếp giảm dần theo avg_discount
    assert bc[0]["avg_discount_pct"] >= bc[-1]["avg_discount_pct"]


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
    import os
    import tempfile

    from extensions.pi import analytics as an
    from extensions.pi import collectors as col

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
    # Shopee collector delegate sang tier chain (ScraperAPI/ZenRows/Jina) —
    # không còn raise NotImplementedError. Không có key → trả None (không raise).
    for _k in ("SCRAPERAPI_KEY", "ZENROWS_KEY", "FIRECRAWL_API_KEY"):
        os.environ.pop(_k, None)
    # Monkeypatch JinaCollector.collect để không gọi mạng thật.
    from extensions.pi.jina_collector import JinaCollector
    orig = JinaCollector.collect
    JinaCollector.collect = lambda self, pid, name, ref_vol=330, channel=None: None
    try:
        pp_shopee = col.collect_product("SHOPEE", "P456", "Heineken Lager 330ml")
    finally:
        JinaCollector.collect = orig
    # Trả None (không có key, Jina trả None) — không raise.
    assert pp_shopee is None
    os.remove(tdb)


@pytest.mark.skip(reason="needs live Tiki (rate-limited); run manually")
def test_collector_tiki_live():
    from extensions.pi import collectors as col
    pp = col.collect_product("TIKI", "P456", "Heineken Lager 330ml")
    assert pp and pp.regular_price > 0


# ---- Tests: price_extract (filter giá rác hotline + brand matching) ----

def test_extract_price_filters_hotline_garbage():
    """Giá hotline "1000 đ/phút" phải bị loại, không trả về 1000."""
    from extensions.pi.price_extract import extract_product_price
    # Chỉ hotline → không có giá sản phẩm → None
    assert extract_product_price("Hotline: 1000 đ/phút (8-21h)") is None
    # Hotline lẫn giá thật → lọc hotline, trả giá/lon (thùng 24 → /24)
    html = "598.800₫ HEINEKEN ### Thùng 24 lon; Hotline 1000 đ/phút"
    val = extract_product_price(html, brand="Heineken")
    assert val == 24950.0  # 598800 / 24 lon — giá/LON apples-to-apples


def test_extract_price_pack_aware_normalizes_box_to_lon():
    """Trang search chỉ có item THÙNG (lon lẻ hết hàng) → trả giá/LON
    bằng pack phát hiện từ context, không trả giá thùng (PR #9).
    Sửa mismatch cho SP như Sư Tử Trắng, Huda.
    """
    from extensions.pi.price_extract import extract_product_price
    # Chỉ 1 item thùng 24 lon, không có lon lẻ → 736000/24 ≈ 30667
    html = "736.000₫ BIA SƯ TỬ TRẮNG ### Thùng 24 lon 330ml"
    assert extract_product_price(html, brand="Sư") == 30666.67
    # Thùng 12 lon → /12
    html12 = "360.000₫ HUDA ### Thùng 12 lon 330ml"
    assert extract_product_price(html12, brand="Huda") == 30000.0
    # "x24" notation
    htmlx = "598.800₫ HEINEKEN ### Bia lon x24"
    assert extract_product_price(htmlx, brand="Heineken") == 24950.0


def test_extract_price_prefers_lon_when_both_present():
    """Trang có cả lon lẻ + thùng → vẫn ưu tiên lon (không chia)."""
    from extensions.pi.price_extract import extract_product_price
    html = "18.500₫ HEINEKEN ### Lon 330ml; 598.800₫ HEINEKEN ### Thùng 24 lon"
    assert extract_product_price(html, brand="Heineken") == 18500.0


def test_extract_price_brand_match_avoids_other_products():
    """Brand match phải ưu tiên giá gần keyword thương hiệu, tránh median
    của toàn bộ sản phẩm trên trang search (bia ngũ hành, Habeco, Rooster).
    """
    from extensions.pi.price_extract import extract_product_price
    # Trang search có nhiều sản phẩm: 681000 (Rooster), 598800 (Heineken).
    html = ("681.000₫ ROOSTER BEERS ### Bia; 598.800₫ HEINEKEN ### Thùng; "
            "635.000₫ HABECO ### Bia")
    # Không brand → median của 3 = 635000 (trung bình các sản phẩm)
    assert extract_product_price(html) == 635000.0
    # Có brand="Heineken" → ưu tiên 598800 (không phải 681000 Rooster)
    assert extract_product_price(html, brand="Heineken") == 598800.0


def test_extract_price_range_and_format():
    """Chấp nhận nhiều format giá VNĐ, loại giá ngoài khoảng 5k-2tr."""
    from extensions.pi.price_extract import extract_product_price
    assert extract_product_price("Giá: 89.000đ") == 89000.0
    assert extract_product_price("Price 1.408.000₫") == 1408000.0
    # Giá quá nhỏ (<5k) → loại
    assert extract_product_price("100đ") is None
    # Giá quá lớn (>2tr) → loại
    assert extract_product_price("5.000.000đ") is None
    # Không có giá → None
    assert extract_product_price("không có giá ở đây") is None


def test_infer_pack_from_price_snaps_to_common_packs():
    """_infer_pack_from_price suy pack từ tỷ số giá thùng/base (PR #11)."""
    from extensions.pi.price_extract import _infer_pack_from_price
    # box=736000, base=30667 → ratio≈24 → pack 24
    assert _infer_pack_from_price(736000.0, 30667.0) == 24
    # box=360000, base=30000 → ratio=12 → pack 12
    assert _infer_pack_from_price(360000.0, 30000.0) == 12
    # box=108000, base=18000 → ratio=6 → pack 6
    assert _infer_pack_from_price(108000.0, 18000.0) == 6
    # box gần base (ratio<2) → None (lon lẻ, không phải thùng)
    assert _infer_pack_from_price(35000.0, 30000.0) is None
    # base=0 → None
    assert _infer_pack_from_price(736000.0, 0.0) is None


def test_extract_price_base_price_inference_when_no_pack_context():
    """Context HTML không nêu pack ("thùng 24") → suy pack từ base_price (PR #11).

    Trước đây: chỉ có thùng 6 lon, không có "thùng 6" text → fallback median
    thùng (108000) → adapter /24 cứng → giá/lon=4500 (sai, quá thấp).
    Sau fix: base_price=18000 → ratio=6 → pack 6 → giá/lon=18000 (đúng).
    """
    from extensions.pi.price_extract import extract_product_price
    # Thùng 6 lon, không có pack text, base_price=18000
    html = "108.000₫ BIA HUDA ### Lon 330ml"
    # Không base_price → fallback median thùng (108000)
    assert extract_product_price(html, brand="Huda") == 108000.0
    # Có base_price=18000 → suy pack 6 → 108000/6=18000
    assert extract_product_price(html, brand="Huda", base_price=18000.0) == 18000.0


def test_extract_price_base_price_inference_thung_12():
    """Thùng 12 lon không có pack text → suy pack 12 từ base_price."""
    from extensions.pi.price_extract import extract_product_price
    html = "360.000₫ HUDA ### Bia lon 330ml"  # không có "thùng 12"
    # base_price=30000 → ratio=12 → pack 12 → 360000/12=30000
    assert extract_product_price(html, brand="Huda", base_price=30000.0) == 30000.0


# ---- Tests: persistent_collector (marker + incremental + notify) ----

def test_persistent_marker_and_incremental(db):
    """collect_smart seed 1 lần (marker), lần 2 cùng giá → skipped (không re-seed)."""
    from extensions.pi import persistent_collector as pc
    from extensions.pi.collectors import PricePoint

    # DB rỗng → chưa có giá thật
    assert pc.has_real_prices(path=db) is False

    # Seed 1 PricePoint → marker đặt
    pp = PricePoint(product_id="P456", sku_id="SKU-P456", channel_id="TIKI",
                    region_id="ONLINE", regular_price=598800.0, promotion_price=None,
                    pack_quantity=1, unit_volume_ml=330, source="tiki-jina", raw={})
    r1 = pc.store_price_point_if_changed(pp, path=db, notify=False)
    assert r1["inserted"] is True
    assert pc.has_real_prices(path=db) is True

    # Quét lại cùng giá → KHÔNG ghi lại (incremental)
    r2 = pc.store_price_point_if_changed(pp, path=db, notify=False)
    assert r2["inserted"] is False
    assert r2["changed"] is False


def test_persistent_changed_price_notifies(db, monkeypatch):
    """Giá thay đổi → observation mới + gọi notify_alert (Discord/Telegram)."""
    from extensions.pi import persistent_collector as pc
    from extensions.pi.collectors import PricePoint

    pp1 = PricePoint(product_id="P456", sku_id="SKU-P456", channel_id="TIKI",
                     region_id="ONLINE", regular_price=598800.0, promotion_price=None,
                     pack_quantity=1, unit_volume_ml=330, source="tiki-jina", raw={})
    pc.store_price_point_if_changed(pp1, path=db, notify=False)

    called = {}
    def fake_notify(alert, **kw):
        called["alert"] = alert
        return {"discord": True, "telegram": True}
    monkeypatch.setattr("extensions.pi.notifier.notify_alert", fake_notify)

    pp2 = PricePoint(product_id="P456", sku_id="SKU-P456", channel_id="TIKI",
                     region_id="ONLINE", regular_price=550000.0, promotion_price=None,
                     pack_quantity=1, unit_volume_ml=330, source="tiki-jina", raw={})
    r = pc.store_price_point_if_changed(pp2, path=db, notify=True)
    assert r["inserted"] is True and r["changed"] is True
    assert r["old_price"] == 598800.0 and r["new_price"] == 550000.0
    assert "alert" in called
    assert called["alert"]["event_type"] == "PRICE_DECREASE"
