"""Test cho HttpCollectAdapter với field config (nối nguồn thật)."""

from __future__ import annotations

import importlib

import pytest

from extensions.collect_adapters import HttpCollectAdapter


def test_parse_response_default_fields():
    a = HttpCollectAdapter()
    data = {"price": 19900, "brand": "Test", "title": "Beer X", "currency": "VND", "province": "HCMC"}
    out = a._parse_response(data, "P999", "api", "http://x/products/P999")
    assert out["price_text"] == "19,900"
    assert out["brand"] == "Test"
    assert out["product_name"] == "Beer X"
    assert out["product_id"] == "P999"


def test_parse_response_custom_fields_via_env(monkeypatch):
    # nguồn trả trường khác: gia -> price, ten -> title
    monkeypatch.setenv("HMIP_PRICE_FIELD_PRICE", "gia")
    monkeypatch.setenv("HMIP_PRICE_FIELD_TITLE", "ten")
    import extensions.collect_adapters as ca

    importlib.reload(ca)
    try:
        a = ca.HttpCollectAdapter()
        data = {"gia": 25000, "ten": "Bia Z", "brand": "ZCorp"}
        out = a._parse_response(data, "PZ", "api", "http://x/PZ")
        assert out["price_text"] == "25,000"
        assert out["product_name"] == "Bia Z"
    finally:
        importlib.reload(ca)


def test_parse_response_missing_price_raises():
    a = HttpCollectAdapter()
    with pytest.raises(Exception):
        a._parse_response({"brand": "X"}, "P1", "api", "http://x/P1")


def test_fetch_requires_base_url(monkeypatch):
    monkeypatch.delenv("HMIP_PRICE_API_BASE", raising=False)
    import extensions.collect_adapters as ca

    importlib.reload(ca)
    try:
        a = ca.HttpCollectAdapter()
        with pytest.raises(Exception):
            a.fetch({"product_id": "P123"})
    finally:
        importlib.reload(ca)
