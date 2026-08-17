"""test_pack_normalize.py — fix mismatch đơn vị thùng/lon (giá 400000).

Root cause: collect lấy giá THÙNG (~400k) nhưng base_price là giá LON (~38k)
→ variance ~479% → ESCALATE sai liên tục. Fix:
1. _parse_pack_volume parse từ tên ITEM thật (thùng 24 vs lon lẻ).
2. _match_best ưu tiên lon lẻ (pack nhỏ) để so sánh apples-to-apples.
3. TikiCollector/ScraperAPI collect parse pack từ item name.
4. _TikiRealAdapter.fetch trả unit_price = eff / pack (giá/lon).
"""

from __future__ import annotations

import importlib

from extensions.pi.collectors import _match_best, _parse_pack_volume


def test_parse_pack_volume_thung_24():
    pack, vol = _parse_pack_volume("Thùng 24 lon bia Heineken (330ml / Lon)")
    assert pack == 24
    assert vol == 330


def test_parse_pack_volume_lon_le():
    pack, vol = _parse_pack_volume("Bia Heineken Lager 330ml")
    assert pack == 1
    assert vol == 330


def test_parse_pack_volume_thung_keyword_default24():
    # 'Thùng bia Heineken 330ml' (không có số) → pack 24 (heuristic)
    pack, _ = _parse_pack_volume("Thùng bia Heineken 330ml")
    assert pack == 24


def test_match_best_prefers_lon_le_over_thung():
    """Khi có cả lon lẻ + thùng, _match_best chọn lon lẻ (pack=1)."""
    items = [
        {"name": "Thùng 24 lon Heineken 330ml", "price": 598800, "list_price": 650000},
        {"name": "Bia Heineken Lager 330ml", "price": 38000, "list_price": 42000},
    ]
    best = _match_best(items, "Heineken Lager 330ml", 330)
    assert best is not None
    pack, _ = _parse_pack_volume(best["name"])
    assert pack == 1, "phải chọn lon lẻ (pack=1), không thùng 24"
    assert best["price"] == 38000


def test_match_best_falls_back_to_thung_when_no_lon_le():
    """Khi chỉ có thùng, vẫn lấy thùng (pack=24) — adapter sẽ chia 24."""
    items = [
        {"name": "Thùng 24 lon Heineken 330ml", "price": 598800, "list_price": 650000},
    ]
    best = _match_best(items, "Heineken Lager 330ml", 330)
    assert best is not None
    pack, _ = _parse_pack_volume(best["name"])
    assert pack == 24


def test_match_best_brand_match_priority():
    """Item cùng brand score cao hơn, dù pack khác."""
    items = [
        {"name": "Bia Tiger 330ml", "price": 20000},          # brand Tiger, pack 1
        {"name": "Bia Heineken Lager 330ml", "price": 38000},  # brand Heineken, pack 1
    ]
    best = _match_best(items, "Heineken Lager 330ml", 330)
    assert best is not None
    assert "heineken" in best["name"].lower()


def test_tiki_collect_parses_pack_from_item_name(monkeypatch):
    """TikiCollector.collect parse pack từ tên ITEM (thùng 24), không tên config (lon 1)."""
    from extensions.pi import collectors as col

    fake_item = {
        "name": "Thùng 24 lon Heineken 330ml",
        "price": 598800,
        "list_price": 650000,
    }

    class FakeTiki(col.TikiCollector):
        def search(self, query, limit=10):
            return [fake_item]

    monkeypatch.setattr(col, "COLLECTORS", {"TIKI": FakeTiki})
    pp = col.collect_product("TIKI", "P456", "Heineken Lager 330ml")
    assert pp is not None
    assert pp.pack_quantity == 24, "pack phải parse từ tên item thùng (24), không config (1)"
    assert pp.regular_price == 598800


def test_tiki_real_adapter_returns_unit_price_per_lon(monkeypatch):
    """_TikiRealAdapter.fetch trả unit_price = eff / pack (giá/lon).

    Giá thùng 598800 / 24 = 24950 → price_text hiển thị giá/lon, không giá thùng.
    """
    monkeypatch.setenv("HMIP_COLLECT_MODE", "http")
    monkeypatch.delenv("HMIP_PRICE_API_BASE", raising=False)
    import extensions.collect_adapters as ca

    importlib.reload(ca)
    try:
        # Mock TikiCollector trả thùng 24 (giá 598800) → adapter chia 24.
        from extensions.pi import collectors as col

        class FakeTiki(col.TikiCollector):
            def search(self, query, limit=10):
                return [{"name": "Thùng 24 lon Heineken 330ml", "price": 598800}]

        monkeypatch.setattr(col, "COLLECTORS", {"TIKI": FakeTiki})
        # Stub Firecrawl/ScraperAPI/ZenRows/Jina để không gọi mạng.
        import extensions.pi.firecrawl_collector as fc
        import extensions.pi.jina_collector as jc
        import extensions.pi.scraperapi_collector as sa
        import extensions.pi.zenrows_collector as zr

        monkeypatch.setattr(fc.FirecrawlCollector, "collect", lambda self, *a, **k: None)
        monkeypatch.setattr(sa.ScraperAPICollector, "collect", lambda self, *a, **k: None)
        monkeypatch.setattr(zr.ZenRowsCollector, "collect", lambda self, *a, **k: None)
        monkeypatch.setattr(jc.JinaCollector, "collect", lambda self, *a, **k: None)

        adapter = ca.build_collect_adapter()
        out = adapter.fetch({"product_id": "P456", "product_name": "Heineken Lager 330ml"})
        # 598800 / 24 = 24950
        got = out["price_text"]
        assert got == "24,950", f"phải là giá/lon (598800/24=24950), got {got}"
    finally:
        importlib.reload(ca)
