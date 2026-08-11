"""Prompt evaluation test for extract_price
(domains/beer/pricing/prompts/extract_price.md), against a versioned
golden dataset. 08_Testing_Standard.md section 10: output format,
required fields, completeness, deterministic structure.

`ExtractPriceSkill` is deterministic (not LLM-backed — see the prompt
file's own "Implementation note"), so this is exact-match evaluation
rather than tolerance-based semantic scoring; "tolerance cho semantic
variation" (section 10) doesn't apply until a real LLM call replaces
it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from domains.beer.pricing.skills.extract_price import ExtractPriceSkill

GOLDEN_PATH = Path(__file__).parent / "golden" / "extract_price_golden.json"

REQUIRED_OUTPUT_FIELDS = {
    "product_id",
    "sku",
    "brand",
    "product_name",
    "price",
    "currency",
    "store",
    "province",
    "capture_time",
    "confidence",
    "source_url",
    "source",
}


def _load_golden() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


GOLDEN = _load_golden()


def test_golden_dataset_is_versioned() -> None:
    assert "version" in GOLDEN
    assert GOLDEN["version"]
    assert GOLDEN["cases"]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_extraction_matches_golden_case(case: dict[str, Any]) -> None:
    skill = ExtractPriceSkill()

    output = skill.run(case["input"])

    for field, expected_value in case["expected"].items():
        assert output[field] == expected_value, (
            f"case '{case['name']}': field '{field}' expected "
            f"{expected_value!r}, got {output[field]!r}"
        )


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_extraction_output_has_exactly_the_required_fields(case: dict[str, Any]) -> None:
    """Output format / completeness (08_Testing_Standard.md section
    10) — every golden case must produce the full contracted shape,
    not just the fields that case happens to assert on."""
    skill = ExtractPriceSkill()

    output = skill.run(case["input"])

    assert set(output.keys()) == REQUIRED_OUTPUT_FIELDS


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_extraction_capture_time_is_valid_iso8601(case: dict[str, Any]) -> None:
    """`capture_time` is derived from wall-clock/`fetched_at` at call
    time, so it isn't golden-compared verbatim — this checks the
    deterministic *structure* (08_Testing_Standard.md section 10)
    instead: it must always be a valid ISO 8601 timestamp."""
    skill = ExtractPriceSkill()

    output = skill.run(case["input"])

    datetime.fromisoformat(output["capture_time"])  # raises ValueError if malformed


def test_extraction_is_deterministic_for_identical_input() -> None:
    skill = ExtractPriceSkill()
    sample_input = {"price_text": "18500", "fetched_at": 1_800_000_000.0}

    first = skill.run(sample_input)
    second = skill.run(sample_input)

    assert first == second
