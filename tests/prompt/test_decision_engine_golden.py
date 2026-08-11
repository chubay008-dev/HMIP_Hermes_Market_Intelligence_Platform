"""Golden-dataset evaluation for PricingDecisionEngine
(domains/beer/pricing/decision_engine.py), grouped under tests/prompt/
per 10_Project_Backlog.md Sprint 5's "Create golden dataset for
extraction/decisioning" — decisioning isn't a literal LLM prompt, but
the backlog explicitly pairs it with extraction's golden-dataset
requirement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from domains.beer.pricing.decision_engine import PricingDecisionEngine

GOLDEN_PATH = Path(__file__).parent / "golden" / "decision_golden.json"


def _load_golden() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


GOLDEN = _load_golden()


def test_golden_dataset_is_versioned() -> None:
    assert "version" in GOLDEN
    assert GOLDEN["version"]
    assert GOLDEN["cases"]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_decision_matches_golden_case(case: dict[str, Any]) -> None:
    engine = PricingDecisionEngine()

    result = engine.build_decision_result(
        case["current_price"], case["base_price"], confidence=case["confidence"]
    )

    assert result.decision == case["expected_decision"], (
        f"case '{case['name']}': expected {case['expected_decision']!r}, "
        f"got {result.decision!r}"
    )


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_decision_result_always_has_a_non_empty_reason(case: dict[str, Any]) -> None:
    engine = PricingDecisionEngine()

    result = engine.build_decision_result(
        case["current_price"], case["base_price"], confidence=case["confidence"]
    )

    assert result.reason


def test_decision_engine_is_deterministic_for_identical_input() -> None:
    engine = PricingDecisionEngine()

    first = engine.build_decision_result(19080.0, 18000.0, confidence=0.9)
    second = engine.build_decision_result(19080.0, 18000.0, confidence=0.9)

    assert first.decision == second.decision
    assert first.reason == second.reason
    assert first.recommended_action == second.recommended_action
