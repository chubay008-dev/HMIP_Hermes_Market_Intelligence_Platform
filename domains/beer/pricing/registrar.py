"""Registers all PRC-001 task handlers into a TaskRegistry.

Used as the `task_registrar` callback for
`core.workflow_engine.WorkflowEngine` — mirrors
`core.bootstrap.BootstrapKernel`'s `task_registrar` constructor-
injection pattern.

Every task also registers a `"rollback"` callable, used by
`WorkflowEngine`'s STRICT-policy compensation loop
(`WF-PRC-001.yaml`'s `compensation_policy: STRICT`). Most are no-ops —
see each `make_*_rollback()`'s own docstring for why — except
`extract`'s, which calls `ExtractPriceSkill.rollback()` (itself
currently a no-op too, since nothing in this vertical slice has real
external side effects yet). The compensation *mechanism* is real and
tested even though none of PRC-001's current tasks have anything
substantive to undo.
"""

from __future__ import annotations

from core.registry import TaskRegistry
from domains.beer.pricing.decision_engine import make_decide_handler, make_decide_rollback
from domains.beer.pricing.skills.alert_price import make_alert_handler, make_alert_rollback
from domains.beer.pricing.skills.collect_price import (
    make_collect_price_handler,
    make_collect_price_rollback,
)
from domains.beer.pricing.skills.compare_price import (
    make_compare_price_handler,
    make_compare_price_rollback,
)
from domains.beer.pricing.skills.enrich_price import (
    make_enrich_price_handler,
    make_enrich_price_rollback,
)
from domains.beer.pricing.skills.extract_price import (
    make_extract_price_handler,
    make_extract_price_rollback,
)
from domains.beer.pricing.skills.validate_price import (
    make_validate_price_handler,
    make_validate_price_rollback,
)

# Reference/base price used by "compare" and "decide". A real
# deployment would resolve this per-product from a reference-price
# source; static injection is sufficient for this vertical slice.
DEFAULT_BASE_PRICE = 18000.0


def register_prc_001_tasks(
    registry: TaskRegistry, *, base_price: float = DEFAULT_BASE_PRICE
) -> None:
    registry.register(
        {
            "name": "collect",
            "handler": make_collect_price_handler(),
            "rollback": make_collect_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "extract",
            "handler": make_extract_price_handler(),
            "rollback": make_extract_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "validate",
            "handler": make_validate_price_handler(),
            "rollback": make_validate_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "enrich",
            "handler": make_enrich_price_handler(),
            "rollback": make_enrich_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "compare",
            "handler": make_compare_price_handler(base_price),
            "rollback": make_compare_price_rollback(),
        }
    )
    registry.register(
        {
            "name": "decide",
            "handler": make_decide_handler(base_price),
            "rollback": make_decide_rollback(),
        }
    )
    registry.register(
        {
            "name": "alert",
            "handler": make_alert_handler(),
            "rollback": make_alert_rollback(),
        }
    )
