"""Unit tests for PricingDecisionEngine (05_Interface_Contract.md
section 4.9)."""

from __future__ import annotations

import pytest

from core.exceptions import DecisionEngineException
from core.models import (
    DECISION_ALERT,
    DECISION_ESCALATE,
    DECISION_HUMAN_REVIEW,
    DECISION_IGNORE,
)
from domains.beer.pricing.decision_engine import PricingDecisionEngine


def test_evaluate_returns_ignore_within_tolerance() -> None:
    engine = PricingDecisionEngine()

    assert engine.evaluate(current_price=18200.0, base_price=18000.0) == DECISION_IGNORE


def test_evaluate_returns_alert_above_alert_threshold() -> None:
    engine = PricingDecisionEngine()

    # 18000 * 1.06 = 19080 -> 6% variance, above ALERT (5%) below ESCALATE (10%)
    assert engine.evaluate(current_price=19080.0, base_price=18000.0) == DECISION_ALERT


def test_evaluate_returns_escalate_above_escalate_threshold() -> None:
    engine = PricingDecisionEngine()

    # 18000 * 1.15 = 20700 -> 15% variance, above ESCALATE (10%)
    assert engine.evaluate(current_price=20700.0, base_price=18000.0) == DECISION_ESCALATE


def test_evaluate_handles_price_decrease_symmetrically() -> None:
    engine = PricingDecisionEngine()

    # 18000 * 0.85 = 15300 -> -15% variance, |variance| above ESCALATE
    assert engine.evaluate(current_price=15300.0, base_price=18000.0) == DECISION_ESCALATE


def test_evaluate_rejects_zero_base_price() -> None:
    engine = PricingDecisionEngine()

    with pytest.raises(DecisionEngineException):
        engine.evaluate(current_price=18000.0, base_price=0.0)


def test_evaluate_rejects_negative_base_price() -> None:
    engine = PricingDecisionEngine()

    with pytest.raises(DecisionEngineException):
        engine.evaluate(current_price=18000.0, base_price=-100.0)


def test_evaluate_does_not_mutate_inputs() -> None:
    engine = PricingDecisionEngine()
    current_price, base_price = 19080.0, 18000.0

    engine.evaluate(current_price=current_price, base_price=base_price)

    assert current_price == 19080.0
    assert base_price == 18000.0


def test_build_decision_result_reflects_evaluate() -> None:
    engine = PricingDecisionEngine()

    result = engine.build_decision_result(19080.0, 18000.0, confidence=0.9)

    assert result.decision == DECISION_ALERT
    assert result.confidence == 0.9
    assert result.recommended_action == "notify_pricing_team"
    assert result.reason


def test_build_decision_result_overrides_to_human_review_on_low_confidence() -> None:
    engine = PricingDecisionEngine()

    result = engine.build_decision_result(19080.0, 18000.0, confidence=0.3)

    assert result.decision == DECISION_HUMAN_REVIEW
    assert result.recommended_action == "route_to_human_review_queue"


def test_build_decision_result_ignore_has_no_recommended_action() -> None:
    engine = PricingDecisionEngine()

    result = engine.build_decision_result(18100.0, 18000.0, confidence=0.9)

    assert result.decision == DECISION_IGNORE
    assert result.recommended_action is None
