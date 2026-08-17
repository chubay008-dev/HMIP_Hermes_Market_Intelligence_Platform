"""test_channels.py — test channel registry + multi-channel collect dispatch.

Kiểm tra:
- Channel registry: TIKI/SHOPEE/LAZADA/TIKTOK/GRABMART có search_url + api_url đúng.
- configured_channels() đọc env HMIP_CHANNELS.
- ScraperAPICollector.collect() dispatch đúng strategy:
  Tiki → API JSON (collect), Shopee/Lazada/TikTok/GrabMart → HTML search (collect_html).
"""

from __future__ import annotations

import os

import extensions.pi.channels as channels
from extensions.pi.channels import REGISTRY, get_channel, configured_channels


def test_registry_has_tiki_shopee_lazada():
    assert "TIKI" in REGISTRY
    assert "SHOPEE" in REGISTRY
    assert "LAZADA" in REGISTRY
    # PR #12: mở rộng registry thêm TikTok Shop + GrabMart.
    assert "TIKTOK" in REGISTRY
    assert "GRABMART" in REGISTRY


def test_tiki_channel_api_strategy():
    t = get_channel("tiki")
    assert t.channel_id == "TIKI"
    assert t.strategy == "api"
    url = t.search_url("Heineken 330ml")
    assert "tiki.vn/search" in url
    api = t.api_url("Heineken 330ml")
    assert api is not None
    assert "tiki.vn/api/v2/products" in api


def test_shopee_channel_html_strategy():
    s = get_channel("shopee")
    assert s.channel_id == "SHOPEE"
    assert s.strategy == "html"
    url = s.search_url("Heineken 330ml")
    assert "shopee.vn/search" in url
    assert "keyword=" in url
    # Shopee không có public API → api_url trả None (phải scrape HTML).
    assert s.api_url("Heineken") is None


def test_lazada_channel_html_strategy():
    l = get_channel("lazada")
    assert l.channel_id == "LAZADA"
    assert l.strategy == "html"
    url = l.search_url("Heineken 330ml")
    assert "lazada.vn" in url
    assert l.api_url("Heineken") is None


def test_tiktok_channel_html_strategy():
    tk = get_channel("tiktok")
    assert tk.channel_id == "TIKTOK"
    assert tk.channel_name == "TikTok Shop"
    assert tk.strategy == "html"
    url = tk.search_url("Heineken 330ml")
    assert "shop.tiktok.com" in url
    assert tk.api_url("Heineken") is None


def test_grabmart_channel_html_strategy():
    gm = get_channel("grabmart")
    assert gm.channel_id == "GRABMART"
    assert gm.channel_name == "GrabMart"
    assert gm.strategy == "html"
    url = gm.search_url("Heineken 330ml")
    assert "grab.com" in url
    assert gm.api_url("Heineken") is None


def test_get_channel_case_insensitive():
    assert get_channel("tiki").channel_id == "TIKI"
    assert get_channel("Shopee").channel_id == "SHOPEE"


def test_get_channel_unknown_raises():
    try:
        get_channel("unknown")
        assert False, "phải raise KeyError"
    except KeyError:
        pass


def test_configured_channels_default_all_five(monkeypatch):
    monkeypatch.delenv("HMIP_CHANNELS", raising=False)
    chans = configured_channels()
    # PR #12: mặc định bật 5 kênh (TIKI, SHOPEE, LAZADA, TIKTOK, GRABMART).
    assert [c.channel_id for c in chans] == ["TIKI", "SHOPEE", "LAZADA", "TIKTOK", "GRABMART"]


def test_configured_channels_multi(monkeypatch):
    monkeypatch.setenv("HMIP_CHANNELS", "tiki,shopee,lazada")
    chans = configured_channels()
    assert [c.channel_id for c in chans] == ["TIKI", "SHOPEE", "LAZADA"]


def test_configured_channels_dedup(monkeypatch):
    monkeypatch.setenv("HMIP_CHANNELS", "tiki,tiki,shopee")
    chans = configured_channels()
    assert [c.channel_id for c in chans] == ["TIKI", "SHOPEE"]


def test_configured_channels_empty_falls_back_default(monkeypatch):
    monkeypatch.setenv("HMIP_CHANNELS", "")
    chans = configured_channels()
    # Empty/garbage env → fallback default 5 kênh (PR #12).
    assert [c.channel_id for c in chans] == ["TIKI", "SHOPEE", "LAZADA", "TIKTOK", "GRABMART"]


def test_scraperapi_dispatches_html_for_shopee(monkeypatch):
    """ScraperAPICollector.collect(channel=SHOPEE) → collect_html (không gọi API)."""
    from extensions.pi.scraperapi_collector import ScraperAPICollector

    col = ScraperAPICollector()
    col.api_key = "fake-key"
    # Monkeypatch collect_html để verify nó được gọi cho SHOPEE.
    called: list[str] = []
    def fake_html(pid, name, chan, ref_vol=330):
        called.append(chan.channel_id)
        return None
    monkeypatch.setattr(col, "collect_html", fake_html)
    # Monkeypatch _api_search để verify nó KHÔNG được gọi cho SHOPEE.
    monkeypatch.setattr(col, "_api_search", lambda *a, **k: (_ for _ in ()).throw(AssertionError("SHOPEE must not use API")))
    chan = get_channel("shopee")
    col.collect("P456", "Heineken Lager 330ml", channel=chan)
    assert called == ["SHOPEE"]


def test_scraperapi_uses_api_for_tiki(monkeypatch):
    """ScraperAPICollector.collect(channel=TIKI) → _api_search (JSON path)."""
    from extensions.pi.scraperapi_collector import ScraperAPICollector

    col = ScraperAPICollector()
    col.api_key = "fake-key"
    api_called: list[str] = []
    def fake_api(query, limit=10):
        api_called.append(query)
        return [{"name": "Heineken 330ml", "price": 22000, "id": "1"}]
    monkeypatch.setattr(col, "_api_search", fake_api)
    monkeypatch.setattr(col, "collect_html", lambda *a, **k: (_ for _ in ()).throw(AssertionError("TIKI must use API")))
    chan = get_channel("tiki")
    pp = col.collect("P456", "Heineken Lager 330ml", channel=chan)
    assert pp is not None
    assert pp.channel_id == "TIKI"
    assert pp.regular_price == 22000.0
    assert api_called


def test_scraperapi_collect_html_shopee_builds_pricepoint(monkeypatch):
    """collect_html cho SHOPEE: scrape HTML → extract_product_price → PricePoint(channel_id=SHOPEE)."""
    from extensions.pi.scraperapi_collector import ScraperAPICollector

    col = ScraperAPICollector()
    col.api_key = "fake-key"
    monkeypatch.setattr(col, "scrape_html", lambda url: "<html>Heineken 22.000₫</html>")
    chan = get_channel("shopee")
    pp = col.collect_html("P456", "Heineken Lager 330ml", chan)
    assert pp is not None
    assert pp.channel_id == "SHOPEE"
    assert "shopee-scraperapi" in pp.source
    assert "shopee.vn/search" in pp.raw["url"]


def test_zenrows_collect_shopee_channel(monkeypatch):
    """ZenRowsCollector.collect(channel=SHOPEE) → PricePoint(channel_id=SHOPEE, source=shopee-zenrows)."""
    from extensions.pi.zenrows_collector import ZenRowsCollector

    col = ZenRowsCollector()
    col.api_key = "fake-key"
    monkeypatch.setattr(col, "scrape_html", lambda url: "<html>Bia 19.500₫</html>")
    chan = get_channel("shopee")
    pp = col.collect("P456", "Heineken Lager 330ml", channel=chan)
    assert pp is not None
    assert pp.channel_id == "SHOPEE"
    assert pp.source == "shopee-zenrows"
    assert "shopee.vn/search" in pp.raw["url"]
