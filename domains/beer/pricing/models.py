"""BeerPrice domain model.

Shape locked by 12_Data_Contract.md section 6.1. `capture_time` is a
required `str` (not `str | None`) per that section's field list.

Validation failures raise `WorkflowExecutionException` — this is a
runtime data-quality failure discovered while processing an already-
structurally-valid task payload (the "validate" task), not a
workflow/task *definition* parsing failure, so it does not fit
`WorkflowParseException`'s scope per 05_Interface_Contract.md section
6. This is a documented interpretation: neither doc names an exact
exception class for domain-entity validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.exceptions import WorkflowExecutionException


@dataclass(frozen=True)
class BeerPrice:
    product_id: str
    sku: str | None
    brand: str
    product_name: str
    price: float
    currency: str
    store: str
    province: str | None
    capture_time: str
    confidence: float
    source_url: str
    source: str

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise WorkflowExecutionException(
                f"BeerPrice.price must be > 0, got {self.price}",
                code="BEER_PRICE_INVALID_PRICE",
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise WorkflowExecutionException(
                f"BeerPrice.confidence must be within 0.0..1.0, got {self.confidence}",
                code="BEER_PRICE_INVALID_CONFIDENCE",
            )
        if not self.product_id:
            raise WorkflowExecutionException(
                "BeerPrice.product_id must not be empty",
                code="BEER_PRICE_MISSING_PRODUCT_ID",
            )
