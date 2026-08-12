"""ai_analyst.py — AI Analyst (Spec §27, §28, §47, §48).

Flow (§27):
    User Question → Intent → Query Planner → Analytics → Evidence Retrieval
    → LLM Reasoning → Confidence → Answer (FACT/EVIDENCE/INFERENCE/
    CONFIDENCE/RECOMMENDATION)

Governance (§48): AI NEVER invents prices/sources, always shows evidence,
prompt_version + model + generated_at persisted (§48 audit fields).

Implementation:
  * Evidence được lấy TỪ DB PI (facts thật), không bao giờ do LLM tự bịa.
  * Nếu có OPENROUTER_API_KEY → gọi LLM để viết inference/recommendation
    từ evidence có sẵn (evidence grounding).
  * Nếu không có key → rule-based fallback (vẫn đầy đủ 5 trường, không
    bao giờ bịa số).
"""

from __future__ import annotations

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from extensions.pi import pi_store, analytics, events
from extensions.pi.models import now_iso

PROMPT_VERSION = "hmip-pi-ai-v1"
MODEL_DEFAULT = os.getenv("HMIP_PI_AI_MODEL", "openai/gpt-4o-mini")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _evidence_for_event(event: dict[str, Any], path: str | None) -> dict[str, Any]:
    """Thu thập evidence thật từ DB cho một price event (Spec §27)."""
    sku = event.get("sku_id")
    # competitor comparison trong cùng comparable universe
    comp = analytics.competitor_comparison(
        filters={"product_id": event.get("product_id")}, path=path)
    # regional pricing
    reg = analytics.regional_pricing(
        filters={"product_id": event.get("product_id")}, path=path)
    # channel comparison
    ch = analytics.channel_comparison(
        filters={"product_id": event.get("product_id")}, path=path)
    # promotions gần đây
    promo = analytics.promotion_intelligence(
        filters={"product_id": event.get("product_id")}, path=path)
    return {
        "event": event,
        "competitor": comp,
        "regional": reg,
        "channel": ch,
        "promotion": promo,
    }


def _rule_based_analysis(event: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Fallback rule-based: FACT (từ DB) + INFERENCE + RECOMMENDATION hợp lý,
    KHÔNG bịa số."""
    change = event.get("change_percent") or 0.0
    direction = "tăng" if change > 0 else "giảm"
    etype = event.get("event_type")
    comp = evidence.get("competitor", {})
    market_avg = comp.get("market_average")
    product_row = next((r for r in comp.get("rows", []) if r.get("product_id") == event.get("product_id")), None)
    product_idx = product_row.get("price_index") if product_row else None

    fact = (
        f"Giá {event.get('product_name')} ({event.get('brand')}) "
        f"trên kênh {event.get('channel_id')} ({event.get('region_id')}) "
        f"{direction} từ {event.get('old_price'):,.0f}₫ → {event.get('new_price'):,.0f}₫ "
        f"({abs(change):.1f}%) vào {(event.get('timestamp') or '')[:10]}."
    )
    inference_parts = []
    if etype == "PROMOTION_ENDED":
        inference_parts.append("Nhiều khả năng do promotion kết thúc (giá quay vềRegular).")
    elif etype == "PROMOTION_STARTED":
        inference_parts.append("Do chiến dịch khuyến mãi mới bắt đầu.")
    else:
        inference_parts.append(f"Biến động {direction} giá vượt ngưỡng cảnh báo.")
    if product_idx is not None:
        if product_idx >= 105:
            inference_parts.append(f"Sản phẩm đang định giá CAO hơn thị trường (index {product_idx}).")
        elif product_idx <= 95:
            inference_parts.append(f"Sản phẩm đang định giá THẤP hơn thị trường (index {product_idx}).")
        else:
            inference_parts.append(f"Giá đang quanh mức tham chiếu thị trường (index {product_idx}).")
    inference = " ".join(inference_parts)

    confidence = 0.82
    if etype in ("PROMOTION_STARTED", "PROMOTION_ENDED"):
        confidence = 0.9

    rec = (
        f"Theo dõi giá đối thủ trong 24–48h. Hiện tại sản phẩm {'cao' if (product_idx or 100) >= 105 else 'thấp'} "
        f"hơn trung bình thị trường; cân nhắc điều chỉnh nếu chênh lệch duy trì >5%."
    )
    return {
        "fact": fact,
        "evidence": json.dumps({
            "competitor_market_avg": market_avg,
            "product_price_index": product_idx,
            "channel_lowest": (evidence.get("channel", {}).get("lowest_channel") or {}).get("channel"),
            "region_count": len(evidence.get("regional", {}).get("regions", [])),
            "recent_promotions": evidence.get("promotion", {}).get("total_promotions", 0),
        }, ensure_ascii=False),
        "inference": inference,
        "confidence": confidence,
        "recommendation": rec,
        "model": "rule-based",
    }


def _llm_analysis(event: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Gọi OpenRouter LLM để viết inference + recommendation TỪ evidence."""
    try:
        import httpx
        ev_text = json.dumps(evidence, ensure_ascii=False, default=str)[:6000]
        prompt = (
            "Bạn là AI Analyst của HMIP (Price Intelligence). Dựa CHỈ vào evidence "
            "bên dưới (trích từ DB thật), hãy phân tích một price event. "
            "TUYỆT ĐỐI không bịa số liệu giá hay nguồn không có trong evidence.\n\n"
            f"EVIDENCE:\n{ev_text}\n\n"
            "Trả về JSON với 3 trường: inference (nguyên nhân có thể), "
            "recommendation (đề xuất cho analyst), confidence (0-1)."
        )
        resp = httpx.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}",
                     "Content-Type": "application/json"},
            json={"model": MODEL_DEFAULT, "messages": [
                {"role": "system", "content": "You output only JSON."},
                {"role": "user", "content": prompt},
            ], "temperature": 0.2},
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        fact = (
            f"Giá {event.get('product_name')} ({event.get('brand')}) "
            f"trên {event.get('channel_id')} ({event.get('region_id')}) "
            f"{'tăng' if (event.get('change_percent') or 0) > 0 else 'giảm'} "
            f"{abs(event.get('change_percent') or 0):.1f}% "
            f"({event.get('old_price'):,.0f}→{event.get('new_price'):,.0f}₫)."
        )
        return {
            "fact": fact,
            "evidence": ev_text[:2000],
            "inference": data.get("inference", ""),
            "confidence": float(data.get("confidence", 0.8)),
            "recommendation": data.get("recommendation", ""),
            "model": MODEL_DEFAULT,
        }
    except Exception as exc:  # noqa: BLE001
        # Fallback an toàn nếu LLM lỗi — không bao giờ crash, không bịa.
        rb = _rule_based_analysis(event, evidence)
        rb["model"] = f"rule-based-fallback ({type(exc).__name__})"
        return rb


def analyze_event(event_id: str, path: str | None = None) -> dict[str, Any]:
    """Phân tích một price event bằng AI Analyst. Trả insight + lưu governance."""
    ev = pi_store.fetch_one(
        """SELECT e.*, p.product_name, b.name AS brand, p.product_id
           FROM pi_price_events e
           JOIN pi_skus s ON s.sku_id = e.sku_id
           JOIN pi_products p ON p.product_id = s.product_id
           JOIN pi_brands b ON b.brand_id = p.brand_id
           WHERE e.event_id = ?""",
        (event_id,), path=path)
    if not ev:
        return {"status": "error", "message": f"event {event_id} not found"}

    evidence = _evidence_for_event(dict(ev), path)
    if OPENROUTER_KEY:
        result = _llm_analysis(dict(ev), evidence)
    else:
        result = _rule_based_analysis(dict(ev), evidence)

    analysis_id = f"ANA-{uuid.uuid4().hex[:12]}"
    pi_store.insert_ai_analysis(
        analysis_id=analysis_id, event_id=event_id,
        question="Tại sao giá thay đổi?",
        fact=result["fact"], evidence=result["evidence"],
        inference=result["inference"], confidence=result["confidence"],
        recommendation=result["recommendation"], model=result["model"],
        prompt_version=PROMPT_VERSION, generated_at=now_iso(),
        input_event_ids=json.dumps([event_id]),
        evidence_ids=json.dumps(list(evidence.keys())),
        path=path,
    )
    return {
        "status": "ok",
        "analysis_id": analysis_id,
        "event_id": event_id,
        "answer": result["fact"] + (f" {result['recommendation']}" if result["recommendation"] else ""),
        "fact": result["fact"],
        "evidence": result["evidence"],
        "inference": result["inference"],
        "confidence": result["confidence"],
        "recommendation": result["recommendation"],
        "model": result["model"],
        "prompt_version": PROMPT_VERSION,
    }


def ask_question(question: str, product_id: str | None = None,
                 path: str | None = None) -> dict[str, Any]:
    """Free-form question (Spec §27 AI Analyst chat).

    Lấy event gần nhất (của product nếu có) làm context, rồi analyze.
    """
    ev_rows = events.list_events(
        filters={"product_id": product_id} if product_id else None, limit=1, path=path)
    if not ev_rows:
        # Không có event → trả tổng quan từ analytics thôi
        kpi = analytics.kpi_overview(
            filters={"product_id": product_id} if product_id else None, path=path)
        return {
            "status": "ok",
            "answer": (
                f"Không có price event đáng kể. Tổng quan: giá TB "
                f"{kpi.get('avg_price')}, biến động {kpi.get('price_change_pct')}%, "
                f"price index {kpi.get('price_index')}."
            ),
            "model": "rule-based",
            "confidence": 0.7,
            "fact": "", "evidence": "", "inference": "", "recommendation": "",
        }
    return analyze_event(ev_rows[0]["event_id"], path=path)


def list_analyses(limit: int = 50, path: str | None = None) -> list[dict[str, Any]]:
    """Governance log: danh sách các phân tích AI đã thực hiện (Spec §48)."""
    rows = pi_store.fetch_all(
        """SELECT analysis_id, event_id, question, model, confidence,
                  recommendation, generated_at
           FROM pi_ai_analyses ORDER BY generated_at DESC LIMIT ?""",
        (limit,), path=path)
    return [dict(r) for r in rows]
