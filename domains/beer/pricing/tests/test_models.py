"""Unit tests for BeerPrice (12_Data_Contract.md section 6.1)."""

from __future__ import annotations

import pytest

from core.exceptions import WorkflowExecutionException
from domains.beer.pricing.models import BeerPrice


def _valid_kwargs() -> dict[str, object]:
    return {
        "product_id": "P123",
        "sku": "SKU-001",
        "brand": "Saigon Beer",
        "product_name": "Saigon Special 330ml",
        "price": 18500.0,
        "currency": "VND",
        "store": "Shopee",
        "province": "HCMC",
        "capture_time": "2026-07-31T10:00:00Z",
        "confidence": 0.93,
        "source_url": "https://example.com/product/123",
        "source": "shopee",
    }


def test_valid_beer_price_constructs() -> None:
    price = BeerPrice(**_valid_kwargs())  # type: ignore[arg-type]

    assert price.product_id == "P123"
    assert price.price == 18500.0


def test_rejects_zero_price() -> None:
    kwargs = _valid_kwargs()
    kwargs["price"] = 0.0

    with pytest.raises(WorkflowExecutionException):
        BeerPrice(**kwargs)  # type: ignore[arg-type]


def test_rejects_negative_price() -> None:
    kwargs = _valid_kwargs()
    kwargs["price"] = -100.0

    with pytest.raises(WorkflowExecutionException):
        BeerPrice(**kwargs)  # type: ignore[arg-type]


def test_rejects_confidence_above_one() -> None:
    kwargs = _valid_kwargs()
    kwargs["confidence"] = 1.5

    with pytest.raises(WorkflowExecutionException):
        BeerPrice(**kwargs)  # type: ignore[arg-type]


def test_rejects_negative_confidence() -> None:
    kwargs = _valid_kwargs()
    kwargs["confidence"] = -0.1

    with pytest.raises(WorkflowExecutionException):
        BeerPrice(**kwargs)  # type: ignore[arg-type]


def test_rejects_empty_product_id() -> None:
    kwargs = _valid_kwargs()
    kwargs["product_id"] = ""

    with pytest.raises(WorkflowExecutionException):
        BeerPrice(**kwargs)  # type: ignore[arg-type]


def test_sku_and_province_accept_none() -> None:
    kwargs = _valid_kwargs()
    kwargs["sku"] = None
    kwargs["province"] = None

    price = BeerPrice(**kwargs)  # type: ignore[arg-type]

    assert price.sku is None
    assert price.province is None
