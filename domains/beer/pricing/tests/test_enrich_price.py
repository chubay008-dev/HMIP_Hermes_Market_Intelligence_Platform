"""Unit tests for enrich_price — the ontology cross-reference step
that closes SPRINT_4_STATUS.md's "ontology not wired into PRC-001"
gap.
"""

from __future__ import annotations

import pytest

from core.context import ExecutionContextFactory
from core.exceptions import WorkflowExecutionException
from domains.beer.pricing.skills.enrich_price import (
    enrich_with_ontology,
    load_default_ontology_dataset,
    make_enrich_price_handler,
)
from knowledge.ontology.models import SKU, Brand, OntologyDataset, Product

CONTEXT = ExecutionContextFactory.create()


def _dataset() -> OntologyDataset:
    return OntologyDataset(
        brands={"B1": Brand(id="B1", name="Saigon Beer")},
        products={"P123": Product(id="P123", brand_id="B1", name="Saigon Special 330ml")},
        skus={"S1": SKU(id="S1", product_id="P123", pack_size="330ml")},
    )


def test_enrich_fills_in_missing_sku_from_ontology() -> None:
    price_record = {"product_id": "P123", "brand": "Saigon Beer", "sku": None}

    enriched = enrich_with_ontology(price_record, _dataset())

    assert enriched["sku"] == "S1"


def test_enrich_does_not_overwrite_an_existing_sku() -> None:
    price_record = {"product_id": "P123", "brand": "Saigon Beer", "sku": "ALREADY-SET"}

    enriched = enrich_with_ontology(price_record, _dataset())

    assert enriched["sku"] == "ALREADY-SET"


def test_enrich_does_not_mutate_the_input_dict() -> None:
    price_record = {"product_id": "P123", "brand": "Saigon Beer", "sku": None}

    enrich_with_ontology(price_record, _dataset())

    assert price_record["sku"] is None


def test_enrich_raises_for_unknown_product() -> None:
    price_record = {"product_id": "UNKNOWN", "brand": "Saigon Beer"}

    with pytest.raises(WorkflowExecutionException) as exc_info:
        enrich_with_ontology(price_record, _dataset())

    assert exc_info.value.code == "ENRICH_PRICE_UNKNOWN_PRODUCT"


def test_enrich_raises_for_brand_mismatch() -> None:
    price_record = {"product_id": "P123", "brand": "Heineken"}

    with pytest.raises(WorkflowExecutionException) as exc_info:
        enrich_with_ontology(price_record, _dataset())

    assert exc_info.value.code == "ENRICH_PRICE_BRAND_MISMATCH"


def test_enrich_allows_missing_brand_field() -> None:
    """No brand to cross-check against isn't itself an error — only a
    *mismatched* brand is."""
    price_record = {"product_id": "P123", "brand": None}

    enriched = enrich_with_ontology(price_record, _dataset())

    assert enriched["product_id"] == "P123"


def test_enrich_handler_reads_validated_price_key() -> None:
    handler = make_enrich_price_handler()

    result = handler(
        {"validated_price": {"product_id": "P123", "brand": "Saigon Beer", "sku": None}},
        CONTEXT,
    )

    assert result["sku"] == "SKU-P123-330"  # from the real shipped master data


def test_load_default_ontology_dataset_loads_real_master_data() -> None:
    dataset = load_default_ontology_dataset()

    assert dataset.get_brand_for_product("P123").name == "Saigon Beer"
