"""enrich_price: cross-references PRC-001's validated price record
against the knowledge/ontology layer (Brand/Product/SKU) for the
"enrich" task (task type "transform").

This is the first and only place in the domain that consults
`knowledge.ontology` — Sprint 4 built the ontology layer standalone
without wiring it into any workflow (see SPRINT_4_STATUS.md's
"Explicitly NOT done"); this closes that gap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.context import ExecutionContext
from core.exceptions import WorkflowExecutionException
from knowledge.ontology.loader import OntologyLoader
from knowledge.ontology.models import OntologyDataset

_MASTER_DIR = Path(__file__).resolve().parents[4] / "knowledge" / "master"


def load_default_ontology_dataset() -> OntologyDataset:
    """Loads the shipped master data (`knowledge/master/*.json`)
    through `OntologyLoader`. Called once at handler-registration time
    (see `make_enrich_price_handler()`), not per-task-execution — the
    ontology dataset doesn't change at runtime in this vertical
    slice."""
    loader = OntologyLoader()
    return loader.load_dataset_from_files(
        brands_path=_MASTER_DIR / "brands.json",
        products_path=_MASTER_DIR / "products.json",
        skus_path=_MASTER_DIR / "skus.json",
    )


def enrich_with_ontology(
    price_record: dict[str, Any], dataset: OntologyDataset
) -> dict[str, Any]:
    """Cross-references `price_record` (a BeerPrice-shaped dict,
    already schema-validated by the "validate" task) against the
    ontology:

    - `product_id` must be a known `Product` — otherwise this is an
      unrecoverable data-quality failure, not something to paper over.
    - `brand` must match the ontology's authoritative `Brand.name` for
      that product — extraction could have gotten this wrong (typos,
      inconsistent source labeling); the ontology is the source of
      truth here.
    - `sku` is populated from the ontology if extraction didn't set
      one (PRC-001's mock collect payload doesn't provide a sku field
      — see SPRINT_3_PRC001_STATUS.md).

    Raises `WorkflowExecutionException` for an unknown product or a
    brand mismatch.
    """
    product_id = price_record.get("product_id")
    product = dataset.products.get(product_id) if product_id else None
    if product is None:
        raise WorkflowExecutionException(
            f"product '{product_id}' is not a known ontology product",
            code="ENRICH_PRICE_UNKNOWN_PRODUCT",
        )

    brand = dataset.brands.get(product.brand_id)
    extracted_brand = price_record.get("brand")
    if brand is not None and extracted_brand and extracted_brand != brand.name:
        raise WorkflowExecutionException(
            f"extracted brand '{extracted_brand}' does not match ontology "
            f"brand '{brand.name}' for product '{product_id}'",
            code="ENRICH_PRICE_BRAND_MISMATCH",
        )

    enriched = dict(price_record)
    if not enriched.get("sku"):
        matching_sku = next(
            (sku for sku in dataset.skus.values() if sku.product_id == product_id), None
        )
        if matching_sku is not None:
            enriched["sku"] = matching_sku.id

    return enriched


def make_enrich_price_handler() -> Any:
    """Adapts `enrich_with_ontology` to the TaskExecutor's TaskHandler
    calling convention. Loads the ontology dataset once, at
    registration time (see `registrar.py`) — not on every call."""
    dataset = load_default_ontology_dataset()

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        validated_price = task_input.get("validated_price") or {}
        return enrich_with_ontology(validated_price, dataset)

    return handler


def make_enrich_price_rollback() -> Any:
    """No-op: enrichment is a pure read/cross-reference against static
    master data, nothing to compensate. See
    `collect_price.py`'s `make_collect_price_rollback()` for why this
    is registered anyway."""

    def rollback(compensation_context: dict[str, Any]) -> None:
        return None

    return rollback
