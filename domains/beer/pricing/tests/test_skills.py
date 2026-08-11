"""Unit tests for PRC-001's individual skill/adapter handlers, tested
in isolation (05_Interface_Contract.md section 8: mockability)."""

from __future__ import annotations

import pytest

from core.context import ExecutionContextFactory
from core.exceptions import WorkflowExecutionException
from domains.beer.pricing.skills.alert_price import make_alert_handler
from domains.beer.pricing.skills.collect_price import (
    CollectPriceAdapter,
    make_collect_price_handler,
)
from domains.beer.pricing.skills.compare_price import (
    compute_variance,
    make_compare_price_handler,
)
from domains.beer.pricing.skills.extract_price import (
    ExtractPriceSkill,
    make_extract_price_handler,
)
from domains.beer.pricing.skills.validate_price import make_validate_price_handler

CONTEXT = ExecutionContextFactory.create()


# --- collect ---------------------------------------------------------


def test_collect_price_adapter_health_is_true() -> None:
    assert CollectPriceAdapter().health() is True


def test_collect_price_adapter_fetch_returns_known_product() -> None:
    payload = CollectPriceAdapter().fetch({"product_id": "P123", "source": "shopee"})

    assert payload["brand"] == "Saigon Beer"
    assert payload["product_id"] == "P123"
    assert "fetched_at" in payload


def test_collect_price_adapter_fetch_raises_for_unknown_product() -> None:
    with pytest.raises(WorkflowExecutionException):
        CollectPriceAdapter().fetch({"product_id": "UNKNOWN", "source": "shopee"})


def test_collect_price_handler_matches_task_handler_signature() -> None:
    handler = make_collect_price_handler()

    result = handler({"product_id": "P123", "source": "shopee"}, CONTEXT)

    assert result["product_id"] == "P123"


# --- extract -----------------------------------------------------------


def test_extract_price_skill_parses_price_text() -> None:
    skill = ExtractPriceSkill()

    output = skill.run(
        {
            "product_id": "P123",
            "brand": "Saigon Beer",
            "product_name": "Saigon Special 330ml",
            "price_text": "18,500",
            "currency": "VND",
            "store": "Shopee",
            "source_url": "https://example.com/product/123",
            "source": "shopee",
            "fetched_at": 1_800_000_000.0,
        }
    )

    assert output["price"] == 18500.0
    assert output["capture_time"]


def test_extract_price_skill_rejects_missing_price_text() -> None:
    skill = ExtractPriceSkill()

    with pytest.raises(WorkflowExecutionException):
        skill.run({"product_id": "P123"})


def test_extract_price_skill_rejects_unparseable_price_text() -> None:
    skill = ExtractPriceSkill()

    with pytest.raises(WorkflowExecutionException):
        skill.run({"price_text": "not-a-number"})


def test_extract_price_skill_rollback_is_a_noop() -> None:
    ExtractPriceSkill().rollback({})  # must not raise


def test_extract_price_handler_reads_raw_payload_key() -> None:
    handler = make_extract_price_handler()

    result = handler(
        {"raw_payload": {"price_text": "20000", "product_id": "P123", "source": "shopee"}},
        CONTEXT,
    )

    assert result["price"] == 20000.0


# --- validate ------------------------------------------------------------


def _valid_structured_price() -> dict[str, object]:
    return {
        "product_id": "P123",
        "sku": None,
        "brand": "Saigon Beer",
        "product_name": "Saigon Special 330ml",
        "price": 18500.0,
        "currency": "VND",
        "store": "Shopee",
        "province": "HCMC",
        "capture_time": "2026-07-31T10:00:00Z",
        "confidence": 0.9,
        "source_url": "https://example.com/product/123",
        "source": "shopee",
    }


def test_validate_price_handler_accepts_valid_payload() -> None:
    handler = make_validate_price_handler()

    result = handler({"structured_price": _valid_structured_price()}, CONTEXT)

    assert result["product_id"] == "P123"


def test_validate_price_handler_rejects_missing_required_field() -> None:
    handler = make_validate_price_handler()
    payload = _valid_structured_price()
    del payload["price"]

    with pytest.raises(WorkflowExecutionException):
        handler({"structured_price": payload}, CONTEXT)


def test_validate_price_handler_rejects_negative_price() -> None:
    handler = make_validate_price_handler()
    payload = _valid_structured_price()
    payload["price"] = -5.0

    with pytest.raises(WorkflowExecutionException):
        handler({"structured_price": payload}, CONTEXT)


# --- compare ------------------------------------------------------------


def test_compute_variance_positive_delta() -> None:
    result = compute_variance(19000.0, 18000.0)

    assert result["delta"] == 1000.0
    assert round(result["delta_percent"], 2) == pytest.approx(5.56, abs=0.01)


def test_compute_variance_rejects_non_positive_base_price() -> None:
    with pytest.raises(WorkflowExecutionException):
        compute_variance(19000.0, 0.0)


def test_compare_price_handler_reads_validated_price_key() -> None:
    handler = make_compare_price_handler(base_price=18000.0)

    result = handler({"validated_price": {"price": 19000.0, "confidence": 0.9}}, CONTEXT)

    assert result["current_price"] == 19000.0
    assert result["confidence"] == 0.9


def test_compare_price_handler_rejects_missing_price() -> None:
    handler = make_compare_price_handler(base_price=18000.0)

    with pytest.raises(WorkflowExecutionException):
        handler({"validated_price": {}}, CONTEXT)


# --- alert ------------------------------------------------------------


def test_alert_handler_does_not_notify_on_ignore() -> None:
    handler = make_alert_handler()

    result = handler({"decision_result": {"decision": "IGNORE"}}, CONTEXT)

    assert result["notified"] is False


def test_alert_handler_notifies_on_alert() -> None:
    handler = make_alert_handler()

    result = handler(
        {
            "decision_result": {
                "decision": "ALERT",
                "recommended_action": "notify_pricing_team",
                "reason": "price variance 6.0% vs base 18000.0",
            }
        },
        CONTEXT,
    )

    assert result["notified"] is True
    assert result["recommended_action"] == "notify_pricing_team"
