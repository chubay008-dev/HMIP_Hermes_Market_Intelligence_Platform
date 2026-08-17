"""collect_price: BaseAdapter implementation for the PRC-001 "collect"
task.

Simulates fetching a raw price payload from an external source
(Shopee, etc.). Real HTTP/scraping integration is out of scope for
this vertical slice (see the Sprint 3 status notes) — the adapter
boundary here exists to prove the architecture layering
(collect -> extract -> validate) with a deterministic, swappable,
mockable implementation, per 03_Domain_Specification.md section 8
("Adapter should be mockable and replaceable").
"""

from __future__ import annotations

import time
from typing import Any

from core.context import ExecutionContext
from core.exceptions import WorkflowExecutionException

# Deterministic mock source data, keyed by (product_id, source). A
# real adapter would call an HTTP client / scraper here instead —
# swapping this out is the whole point of the BaseAdapter boundary.
_MOCK_SOURCE_DATA: dict[tuple[str, str], dict[str, Any]] = {
    ("P123", "shopee"): {
        "brand": "Bia Sài Gòn",
        "product_name": "Saigon Special 330ml",
        "price_text": "18,500",
        "currency": "VND",
        "store": "Shopee",
        "province": "HCMC",
        "source_url": "https://example.com/product/123",
    },
}


class CollectPriceAdapter:
    """Conforms to 05_Interface_Contract.md section 4.1's `BaseAdapter`
    protocol. Contains no business decision logic — only raw
    external-source retrieval."""

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        product_id = request.get("product_id")
        source = request.get("source")
        payload = _MOCK_SOURCE_DATA.get((str(product_id), str(source)))
        if payload is None:
            raise WorkflowExecutionException(
                f"no mock source data for product_id={product_id!r} "
                f"source={source!r}",
                code="COLLECT_PRICE_SOURCE_UNAVAILABLE",
            )
        return {
            **payload,
            "product_id": product_id,
            "source": source,
            "fetched_at": time.time(),
        }

    def health(self) -> bool:
        return True


def make_collect_price_handler() -> Any:
    """Adapts CollectPriceAdapter to the TaskExecutor's TaskHandler
    calling convention (`(task_input, context) -> dict`), since
    BaseAdapter's own method name (`fetch`) differs from that
    convention."""
    adapter = CollectPriceAdapter()

    def handler(task_input: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return adapter.fetch(task_input)

    return handler


def make_collect_price_rollback() -> Any:
    """No-op: `BaseAdapter`'s protocol only defines `fetch()`/
    `health()` — read operations, nothing to compensate. Registered
    anyway (with `core.workflow_engine.WorkflowEngine`'s STRICT-policy
    compensation loop) so that mechanism is exercised uniformly across
    every task in the workflow, not only the ones that happen to need
    it — see `domains/beer/pricing/skills/extract_price.py`'s
    `make_extract_price_rollback()` for the one task in this pack that
    actually has a `rollback()` method to call."""

    def rollback(compensation_context: dict[str, Any]) -> None:
        return None

    return rollback
