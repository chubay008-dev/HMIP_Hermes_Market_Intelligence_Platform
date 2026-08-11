"""Ontology entities: Brand, Product, SKU, and OntologyDataset.

Shape per `knowledge/ontology/core_schema.json`'s "Brand"/"Product"/
"SKU" definitions. Relationships: `Product.brand_id` references a
`Brand.id`; `SKU.product_id` references a `Product.id`. Per-entity
shape is validated here (via `__post_init__`); cross-entity
referential integrity across a whole dataset is NOT checked here —
that's `knowledge.ontology.loader.OntologyLoader.load_dataset()`'s job
(mirrors `core.workflow.WorkflowDefinition`'s split: per-entity shape
in the dataclass, cross-entity/DAG-level checks in a loader).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.exceptions import KnowledgeValidationException


@dataclass(frozen=True)
class Brand:
    id: str
    name: str
    country: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise KnowledgeValidationException(
                "Brand.id must not be empty", code="ONTOLOGY_BRAND_MISSING_ID"
            )
        if not self.name:
            raise KnowledgeValidationException(
                "Brand.name must not be empty", code="ONTOLOGY_BRAND_MISSING_NAME"
            )


@dataclass(frozen=True)
class Product:
    id: str
    brand_id: str
    name: str
    category: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise KnowledgeValidationException(
                "Product.id must not be empty", code="ONTOLOGY_PRODUCT_MISSING_ID"
            )
        if not self.brand_id:
            raise KnowledgeValidationException(
                "Product.brand_id must not be empty",
                code="ONTOLOGY_PRODUCT_MISSING_BRAND_ID",
            )
        if not self.name:
            raise KnowledgeValidationException(
                "Product.name must not be empty", code="ONTOLOGY_PRODUCT_MISSING_NAME"
            )


@dataclass(frozen=True)
class SKU:
    id: str
    product_id: str
    pack_size: str
    barcode: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise KnowledgeValidationException(
                "SKU.id must not be empty", code="ONTOLOGY_SKU_MISSING_ID"
            )
        if not self.product_id:
            raise KnowledgeValidationException(
                "SKU.product_id must not be empty",
                code="ONTOLOGY_SKU_MISSING_PRODUCT_ID",
            )
        if not self.pack_size:
            raise KnowledgeValidationException(
                "SKU.pack_size must not be empty", code="ONTOLOGY_SKU_MISSING_PACK_SIZE"
            )


@dataclass(frozen=True)
class OntologyDataset:
    """Result of `OntologyLoader.load_dataset()` — a validated,
    cross-referenced knowledge dataset. Keyed by entity id for O(1)
    lookup."""

    brands: dict[str, Brand]
    products: dict[str, Product]
    skus: dict[str, SKU]

    def get_brand_for_product(self, product_id: str) -> Brand:
        return self.brands[self.products[product_id].brand_id]

    def get_product_for_sku(self, sku_id: str) -> Product:
        return self.products[self.skus[sku_id].product_id]
