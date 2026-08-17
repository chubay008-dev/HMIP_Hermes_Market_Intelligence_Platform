"""Unit tests for the ontology layer (Brand/Product/SKU +
OntologyLoader), per 15_Acceptance_Criteria.md section 3 (Sprint 4:
"Ontology load/validate thành công", "Brand/Product/SKU schema rõ
ràng") and section 4 ("Ontology versioned", "Entities rõ quan hệ").
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import KnowledgeValidationException
from knowledge.ontology.loader import OntologyLoader
from knowledge.ontology.models import SKU, Brand, Product

MASTER_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "master"


# --- entity-level validation ---------------------------------------------


def test_brand_constructs_with_valid_fields() -> None:
    brand = Brand(id="BRAND-SAIGON", name="Saigon Beer", country="VN")

    assert brand.id == "BRAND-SAIGON"
    assert brand.country == "VN"


def test_brand_rejects_empty_id() -> None:
    with pytest.raises(KnowledgeValidationException):
        Brand(id="", name="Saigon Beer")


def test_brand_rejects_empty_name() -> None:
    with pytest.raises(KnowledgeValidationException):
        Brand(id="BRAND-SAIGON", name="")


def test_product_rejects_empty_brand_id() -> None:
    with pytest.raises(KnowledgeValidationException):
        Product(id="P123", brand_id="", name="Saigon Special")


def test_sku_rejects_empty_pack_size() -> None:
    with pytest.raises(KnowledgeValidationException):
        SKU(id="SKU-1", product_id="P123", pack_size="")


# --- OntologyLoader: schema loading and versioning ------------------------


def test_loader_exposes_schema_version() -> None:
    loader = OntologyLoader()

    assert loader.version == "1.0.0"


def test_loader_raises_for_missing_schema_file(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeValidationException):
        OntologyLoader(schema_path=tmp_path / "missing.json")


# --- OntologyLoader: per-entity schema validation -------------------------


def test_load_brand_accepts_valid_data() -> None:
    loader = OntologyLoader()

    brand = loader.load_brand({"id": "BRAND-SAIGON", "name": "Saigon Beer", "country": "VN"})

    assert brand.name == "Saigon Beer"


def test_load_brand_rejects_unknown_extra_field() -> None:
    loader = OntologyLoader()

    with pytest.raises(KnowledgeValidationException):
        loader.load_brand({"id": "BRAND-SAIGON", "name": "Saigon Beer", "unexpected": True})


def test_load_product_rejects_missing_required_field() -> None:
    loader = OntologyLoader()

    with pytest.raises(KnowledgeValidationException):
        loader.load_product({"id": "P123", "name": "Saigon Special"})  # missing brand_id


# --- OntologyLoader: dataset-level referential integrity ------------------


def test_load_dataset_accepts_valid_referenced_entities() -> None:
    loader = OntologyLoader()

    dataset = loader.load_dataset(
        brands=[{"id": "B1", "name": "Saigon Beer"}],
        products=[{"id": "P1", "brand_id": "B1", "name": "Saigon Special"}],
        skus=[{"id": "S1", "product_id": "P1", "pack_size": "330ml"}],
    )

    assert dataset.get_brand_for_product("P1").id == "B1"
    assert dataset.get_product_for_sku("S1").id == "P1"


def test_load_dataset_rejects_product_with_unknown_brand() -> None:
    loader = OntologyLoader()

    with pytest.raises(KnowledgeValidationException):
        loader.load_dataset(
            brands=[{"id": "B1", "name": "Saigon Beer"}],
            products=[{"id": "P1", "brand_id": "UNKNOWN", "name": "Saigon Special"}],
            skus=[],
        )


def test_load_dataset_rejects_sku_with_unknown_product() -> None:
    loader = OntologyLoader()

    with pytest.raises(KnowledgeValidationException):
        loader.load_dataset(
            brands=[{"id": "B1", "name": "Saigon Beer"}],
            products=[{"id": "P1", "brand_id": "B1", "name": "Saigon Special"}],
            skus=[{"id": "S1", "product_id": "UNKNOWN", "pack_size": "330ml"}],
        )


# --- OntologyLoader: real shipped master data -----------------------------


def test_load_dataset_from_files_accepts_real_master_data() -> None:
    loader = OntologyLoader()

    dataset = loader.load_dataset_from_files(
        brands_path=MASTER_DIR / "brands.json",
        products_path=MASTER_DIR / "products.json",
        skus_path=MASTER_DIR / "skus.json",
    )

    assert dataset.get_brand_for_product("P123").name == "Bia Sài Gòn"
    assert dataset.get_product_for_sku("SKU-P123-330").id == "P123"


def test_load_dataset_from_files_raises_for_missing_file(tmp_path: Path) -> None:
    loader = OntologyLoader()

    with pytest.raises(KnowledgeValidationException):
        loader.load_dataset_from_files(
            brands_path=tmp_path / "missing.json",
            products_path=MASTER_DIR / "products.json",
            skus_path=MASTER_DIR / "skus.json",
        )
