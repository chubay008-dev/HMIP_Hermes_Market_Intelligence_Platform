"""OntologyLoader: loads and validates the HMIP core ontology
(Brand/Product/SKU) plus a full knowledge dataset built from it.

Satisfies 15_Acceptance_Criteria.md section 3's Sprint 4 criteria
("Ontology load/validate thành công", "Brand/Product/SKU schema rõ
ràng") and section 4's Knowledge module criteria ("Ontology
versioned", "Entities rõ quan hệ").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from core.exceptions import KnowledgeValidationException
from knowledge.ontology.models import SKU, Brand, OntologyDataset, Product

_SCHEMA_PATH = Path(__file__).resolve().parent / "core_schema.json"


class OntologyLoader:
    """Loads `core_schema.json` once at construction, then validates
    Brand/Product/SKU records against it and against each other's
    referential integrity. Reusable across any number of `load_*`
    calls."""

    def __init__(self, schema_path: Path | None = None) -> None:
        self._schema = self._load_schema(schema_path or _SCHEMA_PATH)

    @property
    def version(self) -> str:
        """Ontology versioning per 17_Glossary.md's "Ontology" entry
        and the Sprint 4 acceptance criterion "Ontology versioned"."""
        version = self._schema.get("version")
        if not isinstance(version, str) or not version:
            raise KnowledgeValidationException(
                "ontology schema is missing a 'version' field",
                code="ONTOLOGY_MISSING_VERSION",
            )
        return version

    def _load_schema(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise KnowledgeValidationException(
                f"ontology schema not found: {path}", code="ONTOLOGY_SCHEMA_NOT_FOUND"
            )
        try:
            schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KnowledgeValidationException(
                f"invalid JSON in ontology schema {path}: {exc}",
                code="ONTOLOGY_SCHEMA_INVALID_JSON",
            ) from exc
        return schema

    def _validate_against_definition(self, entity_type: str, data: dict[str, Any]) -> None:
        definition = self._schema.get("definitions", {}).get(entity_type)
        if definition is None:
            raise KnowledgeValidationException(
                f"ontology schema has no definition for '{entity_type}'",
                code="ONTOLOGY_UNKNOWN_ENTITY_TYPE",
            )
        try:
            jsonschema.validate(instance=data, schema=definition)
        except jsonschema.ValidationError as exc:
            raise KnowledgeValidationException(
                f"{entity_type} failed schema validation: {exc.message}",
                code="ONTOLOGY_ENTITY_SCHEMA_MISMATCH",
            ) from exc

    def load_brand(self, data: dict[str, Any]) -> Brand:
        self._validate_against_definition("Brand", data)
        return Brand(**data)

    def load_product(self, data: dict[str, Any]) -> Product:
        self._validate_against_definition("Product", data)
        return Product(**data)

    def load_sku(self, data: dict[str, Any]) -> SKU:
        self._validate_against_definition("SKU", data)
        return SKU(**data)

    def load_dataset(
        self,
        *,
        brands: list[dict[str, Any]],
        products: list[dict[str, Any]],
        skus: list[dict[str, Any]],
    ) -> OntologyDataset:
        """Loads and validates a full knowledge dataset, including
        cross-entity referential integrity (`Product.brand_id` must
        reference a known `Brand.id`; `SKU.product_id` must reference
        a known `Product.id`) — this is the "ontology load/validate"
        acceptance criterion, and 15_Acceptance_Criteria.md section
        4's "Entities rõ quan hệ"."""
        loaded_brands: dict[str, Brand] = {}
        for raw_brand in brands:
            brand = self.load_brand(raw_brand)
            loaded_brands[brand.id] = brand

        loaded_products: dict[str, Product] = {}
        for raw_product in products:
            product = self.load_product(raw_product)
            if product.brand_id not in loaded_brands:
                raise KnowledgeValidationException(
                    f"product '{product.id}' references unknown brand_id "
                    f"'{product.brand_id}'",
                    code="ONTOLOGY_UNKNOWN_BRAND_REFERENCE",
                )
            loaded_products[product.id] = product

        loaded_skus: dict[str, SKU] = {}
        for raw_sku in skus:
            sku = self.load_sku(raw_sku)
            if sku.product_id not in loaded_products:
                raise KnowledgeValidationException(
                    f"sku '{sku.id}' references unknown product_id "
                    f"'{sku.product_id}'",
                    code="ONTOLOGY_UNKNOWN_PRODUCT_REFERENCE",
                )
            loaded_skus[sku.id] = sku

        return OntologyDataset(brands=loaded_brands, products=loaded_products, skus=loaded_skus)

    def load_dataset_from_files(
        self, *, brands_path: Path, products_path: Path, skus_path: Path
    ) -> OntologyDataset:
        """Convenience wrapper around `load_dataset()` that reads the
        three master-data JSON files directly (see
        `knowledge/master/`)."""
        return self.load_dataset(
            brands=self._read_json_list(brands_path),
            products=self._read_json_list(products_path),
            skus=self._read_json_list(skus_path),
        )

    def _read_json_list(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            raise KnowledgeValidationException(
                f"master data file not found: {path}", code="ONTOLOGY_MASTER_DATA_NOT_FOUND"
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise KnowledgeValidationException(
                f"invalid JSON in master data file {path}: {exc}",
                code="ONTOLOGY_MASTER_DATA_INVALID_JSON",
            ) from exc
        if not isinstance(data, list):
            raise KnowledgeValidationException(
                f"master data file must contain a JSON array: {path}",
                code="ONTOLOGY_MASTER_DATA_INVALID_SHAPE",
            )
        return data
