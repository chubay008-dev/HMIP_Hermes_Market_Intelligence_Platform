"""run_workflow.py — NỐI WORKFLOW ENGINE VÀO RUNTIME THẬT (fix F-01).

Trước đây `WorkflowEngine` chỉ được gọi từ `tests/`. Module này là
entrypoint sản phẩm: chạy WF-PRC-001 cho một sản phẩm, thu thập kết
quả từng bước, rồi lưu vào SQLite để web đọc lại.

KHÔNG sửa `core/`. Chỉ dùng public API của kernel:
    WorkflowEngine(workflow_lookup=, task_registrar=, event_bus=, lineage_tracer=)
    engine.load(id) / engine.execute(workflow, context)

Hai vấn đề của bản gốc được xử lý ở đây:
  * `base_price` không còn là hằng số 18000 cho mọi sản phẩm — được
    resolve theo từng product (env override → catalog → mặc định).
  * `engine.execute()` chỉ trả output của task CUỐI (alert), nên các
    số liệu trung gian (giá, delta%) được thu qua EventBus subscriber.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.event_bus import EventBus
from core.lineage import PersistentLineageTracer
from core.workflow_engine import WorkflowEngine
from domains.beer.pricing.decision_engine import make_decide_handler
from domains.beer.pricing.skills.alert_price import make_alert_handler
from domains.beer.pricing.skills.compare_price import make_compare_price_handler
from domains.beer.pricing.skills.enrich_price import make_enrich_price_handler
from domains.beer.pricing.skills.extract_price import make_extract_price_handler
from domains.beer.pricing.skills.validate_price import make_validate_price_handler
from extensions.collect_adapters import make_collect_handler, make_collect_rollback
from extensions.db import (
    init_db,
    record_price_point,
    set_base_price_if_absent,
    upsert_product,
)
from extensions import db as _db_module

_REPO_ROOT = Path(__file__).resolve().parent.parent
WF_PATH = _REPO_ROOT / "domains" / "beer" / "pricing" / "workflows" / "WF-PRC-001.yaml"

# Giá tham chiếu mỗi sản phẩm. Triển khai thật nên đọc từ DB/ERP;
# ở đây tách khỏi hằng số cứng DEFAULT_BASE_PRICE của registrar gốc.
_BASE_PRICES: dict[str, float] = {
    "P123": 18000.0,
    "P456": 22000.0,
}
_FALLBACK_BASE_PRICE = 18000.0


def resolve_base_price(product_id: str) -> float | None:
    """Độ ưu tiên base_price:
    1. DB (mốc tự động gán từ lần quét đầu qua set_base_price_if_absent)
    2. env HMIP_BASE_PRICE_<ID>
    3. catalog _BASE_PRICES
    4. env HMIP_DEFAULT_BASE_PRICE
    5. None → caller sẽ gán = giá quét đầu (tự động)
    """
    db_bp = _db_module.get_base_price(product_id)
    if db_bp is not None:
        return db_bp
    env = os.getenv(f"HMIP_BASE_PRICE_{product_id}")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    if product_id in _BASE_PRICES:
        return _BASE_PRICES[product_id]
    env = os.getenv("HMIP_DEFAULT_BASE_PRICE")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return None  # tự động: gán = giá quét đầu


class _DualLineageTracer:
    """Vừa ghi lineage bền vững ra file (audit trail), vừa giữ output
    từng step trong memory để caller đọc lại.

    Cần thiết vì `engine.execute()` chỉ trả output của task cuối, còn
    EventBus chỉ phát {task_id, status} — không kèm dữ liệu. Tuân thủ
    LineageTracer protocol: record_trace() + list_records().
    """

    def __init__(self) -> None:
        self._persistent = PersistentLineageTracer()
        self._steps: dict[str, Any] = {}

    def record_trace(
        self, step_id: str, input_val: Any, output_val: Any, model_info: str
    ) -> None:
        self._persistent.record_trace(step_id, input_val, output_val, model_info)
        if not step_id.startswith("rollback:"):
            self._steps[step_id] = output_val

    def list_records(self):
        return self._persistent.list_records()

    def step_outputs(self) -> dict[str, Any]:
        return dict(self._steps)


def _make_enrich_fallback():
    """Bọc enrich handler gốc.

    Nếu SP có trong ontology → enrich bình thường.
    Nếu KHÔNG (SP mới thêm từ giao diện) → enrich gốc raise, ta fallback
    trả structure GIỐNG HỆT enrich thành công (có price/brand/product_name)
    từ dữ liệu validate, để compare/decide chạy tiếp. Không sửa code core.
    """
    base = make_enrich_price_handler()

    def handler(task_input: dict[str, Any], context: Any) -> dict[str, Any]:
        try:
            return base(task_input, context)
        except Exception:  # noqa: BLE001
            # task_input ở đây là output của validate (đã có price, brand...)
            price = task_input.get("price")
            return {
                "product_id": task_input.get("product_id"),
                "sku": task_input.get("sku") or f"SKU-{task_input.get('product_id')}",
                "brand": task_input.get("brand") or "Unknown",
                "product_name": task_input.get("product_name")
                or task_input.get("product_id", ""),
                "price": price,
                "validated_price": {
                    "price": price,
                    "currency": task_input.get("currency", "VND"),
                    "confidence": task_input.get("confidence", 0.9),
                },
                "currency": task_input.get("currency", "VND"),
                "store": task_input.get("store") or task_input.get("source", "manual"),
                "province": task_input.get("province", "N/A"),
                "capture_time": task_input.get("capture_time"),
                "confidence": task_input.get("confidence", 0.9),
                "source_url": task_input.get("source_url", ""),
                "source": task_input.get("source", "manual"),
                "enriched": False,
            }

    return handler


def _build_registrar(base_price: float):
    """Đăng ký 7 task; chỉ 'collect' được thay bằng adapter thật."""

    def registrar(registry) -> None:
        noop = lambda cc: None  # noqa: E731
        registry.register({
            "name": "collect",
            "handler": make_collect_handler(),
            "rollback": make_collect_rollback(),
        })
        registry.register({
            "name": "extract",
            "handler": make_extract_price_handler(),
            "rollback": noop,
        })
        registry.register({
            "name": "validate",
            "handler": make_validate_price_handler(),
            "rollback": noop,
        })
        registry.register({
            "name": "enrich",
            "handler": make_enrich_price_handler(),
            "rollback": noop,
        })
        registry.register({
            "name": "compare",
            "handler": make_compare_price_handler(base_price),
            "rollback": noop,
        })
        registry.register({
            "name": "decide",
            "handler": make_decide_handler(base_price),
            "rollback": noop,
        })
        registry.register({
            "name": "alert",
            "handler": make_alert_handler(),
            "rollback": noop,
        })

    return registrar


def run_prc_001(
    product_id: str,
    source: str = "demo",
    market: str = "VN",
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Chạy WF-PRC-001 cho một sản phẩm.

    Trả về dict kết quả của engine, bổ sung khoá `steps` chứa output
    từng task (thu qua EventBus) và `saved` cho biết đã ghi DB chưa.
    """
    if persist:
        init_db()

    base_price = resolve_base_price(product_id)
    auto_base = False
    if base_price is None:
        # Chưa có mốc → dùng giá quét đầu làm base_price (tự động)
        auto_base = True
    # Truyền base_price tạm = 1.0 nếu auto (kernel không chia cho None);
    # delta% sẽ tính lại ở dưới sau khi có mốc thật.
    eff_base = base_price if base_price is not None else 1.0
    bus = EventBus()

    # engine.execute() chỉ trả output của task CUỐI (alert). Số liệu
    # trung gian (giá, delta%) lấy qua lineage tracer — event bus chỉ
    # phát {task_id, status}, không kèm output.
    tracer = _DualLineageTracer()

    engine = WorkflowEngine(
        workflow_lookup={"WF-PRC-001": WF_PATH},
        task_registrar=_build_registrar(eff_base),
        event_bus=bus,
        lineage_tracer=tracer,
    )

    workflow = engine.load("WF-PRC-001")
    result = engine.execute(
        workflow,
        {"product_id": product_id, "source": source, "market": market},
    )
    steps = tracer.step_outputs()
    result["steps"] = steps
    result["base_price"] = base_price
    result["saved"] = False

    if persist and result.get("status") == "COMPLETED":
        enriched = steps.get("enrich") or {}
        compared = steps.get("compare") or {}
        decided = steps.get("decide") or {}
        alerted = result.get("output") or {}

        price = compared.get("current_price") or enriched.get("price")
        if price is not None:
            # Tự động gán mốc: lần quét đầu làm base_price
            if auto_base:
                base_price = _db_module.set_base_price_if_absent(product_id, float(price))
                # tính lại delta% so với mốc thật
                delta = ((float(price) - base_price) / base_price * 100.0) if base_price else 0.0
                compared = {**compared, "delta_percent": delta}
                # tính lại quyết định (ngưỡng 2/5)
                decide_handler = make_decide_handler(base_price)
                decided = decide_handler(
                    {"compare_result": {"current_price": float(price), "confidence": 0.9}},
                    None,
                )
                steps["compare"] = compared
                steps["decide"] = decided
                result["steps"] = steps
                result["base_price"] = base_price
            upsert_product(
                product_id=product_id,
                name=enriched.get("product_name") or product_id,
                brand=enriched.get("brand"),
                source=source,
                base_price=base_price,
            )
            record_price_point(
                product_id=product_id,
                price=float(price),
                currency=enriched.get("currency", "VND"),
                decision=decided.get("decision") or alerted.get("decision"),
                delta_percent=compared.get("delta_percent"),
                source_url=enriched.get("source_url"),
            )
            result["saved"] = True

    return result


def main() -> int:
    """CLI: python -m extensions.run_workflow <product_id> [source]"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Chạy WF-PRC-001")
    parser.add_argument("product_id", help="ví dụ: P123")
    parser.add_argument("source", nargs="?", default="demo")
    parser.add_argument("--no-save", action="store_true", help="không ghi DB")
    args = parser.parse_args()

    result = run_prc_001(args.product_id, args.source, persist=not args.no_save)
    printable = {k: v for k, v in result.items() if k != "input"}
    print(json.dumps(printable, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
