#!/usr/bin/env python3
"""reconcile_prices.py — Hòa giải giá từ NHIỀU nguồn về knowledge/master/prices_real.json.

Nguyên tắc (xem ADR trong docs):
  - Mỗi nguồn ghi raw riêng; CHỈ script này được ghi vào master.
  - Không fuzzy matching: ánh xạ SKU qua config/beer_scan_sku_map.json (thủ công).
  - Quy tắc merge theo confidence:
      * >=2 nguồn độc lập lệch <5%  -> high, lấy TRUNG VỊ
      * đúng 1 nguồn              -> medium
      * 2 nguồn lệch >20%         -> KHÔNG ghi, flag "conflict" (báo user duyệt)
      * biến động >30% so giá cũ  -> flag "anomaly" (nghi quét nhầm thùng/lẻ)
  - Nguồn cập nhật vào field channels{} sẵn có của schema prices_real.json.

Chạy:
    python3 scripts/reconcile_prices.py            # merge + ghi master
    python3 scripts/reconcile_prices.py --dry-run  # chỉ in kết quả, không ghi
"""
from __future__ import annotations
import argparse
import datetime
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MASTER = REPO / "knowledge" / "master"
DYNAMIC = REPO / "knowledge" / "dynamic"
RAW = REPO / "data" / "raw"
SKU_MAP = REPO / "config" / "beer_scan_sku_map.json"

CONFLICT_PCT = 0.20   # 2 cụm nguồn lệch >20% -> conflict
ANOMALY_PCT = 0.30    # lệch >30% so giá cũ -> anomaly
AGREE_PCT = 0.05      # nguồn độc lập lệch <5% -> đồng thuận -> high


def filter_outliers(vals):
    """Loại giá rác (nhầm thùng/lẻ, giá hộp quà) bằng IQR trước khi so nguồn.
    vals: list (value, source). Trả list đã lọc. Cần >=4 điểm mới lọc."""
    if len(vals) < 4:
        return vals
    vs = sorted(v[0] for v in vals)
    q1 = vs[len(vs) // 4]
    q3 = vs[(3 * len(vs)) // 4]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    kept = [v for v in vals if lo <= v[0] <= hi]
    # nếu lọc mạnh tay quá (mất >60%) thì bỏ lọc — dữ liệu phân tán thật
    return kept if len(kept) >= max(2, int(0.4 * len(vals))) else vals


def load_beer_scan():
    """Đọc knowledge/dynamic/beer_scan/latest/data_overrides.json, map qua SKU map.
    Trả {product_id: {"case"|"single": (price, source_label, evidence)}}"""
    f = DYNAMIC / "beer_scan" / "latest" / "data_overrides.json"
    if not f.exists():
        return {}, ["beer_scan: không có data_overrides.json"]
    overrides = json.loads(f.read_text(encoding="utf-8"))
    mapping = json.loads(SKU_MAP.read_text(encoding="utf-8"))["map"]
    out, skipped = {}, []
    for key, val in overrides.items():
        price = val[0] if isinstance(val, list) and val else None
        evidence = (val[1] if isinstance(val, list) and len(val) > 1 else "")[:120]
        m = mapping.get(key)
        if not m or not m.get("product_id"):
            skipped.append(key)
            continue
        pid, ptype = m["product_id"], m.get("price_type", "case")
        src = key.split("@")[0]  # TGD / BNK / GO / KAM ...
        entry = out.setdefault(pid, {})
        # nguồn đầu tiên thắng nếu trùng loại
        entry.setdefault(ptype, (price, src.lower(), evidence))
    return out, skipped


def load_raw_sources():
    """Đọc mọi file data/raw/<source>.json do collect_sources.py tạo.
    Trả {product_id: [ {case, single, source, evidence} ]}"""
    out = {}
    if not RAW.exists():
        return out
    for f in sorted(RAW.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        src = doc.get("source", f.stem)
        for it in doc.get("items", []):
            pid = it.get("product_id")
            if not pid:
                continue
            out.setdefault(pid, []).append({
                "case": it.get("price_case_vnd"),
                "single": it.get("price_single_vnd"),
                "source": src, "evidence": it.get("url") or "",
            })
    return out


def collect_candidates(prices_doc):
    """Gom mọi nguồn giá hiện có: beer_scan mới + data/raw adapters + channels{} cũ."""
    beer_scan, skipped = load_beer_scan()
    raw_sources = load_raw_sources()
    by_pid = {p["product_id"]: p for p in prices_doc["prices"]}
    result = {}
    for pid, prod in by_pid.items():
        cands = []  # list dict(price_case, price_single, source, confidence)
        # nguồn mới từ beer-scan
        bs = beer_scan.get(pid, {})
        if "case" in bs:
            c, src, ev = bs["case"]
            cands.append({"case": c, "single": bs.get("single", (None,))[0],
                          "source": f"beer_scan/{src}", "evidence": ev})
        elif "single" in bs:
            s, src, ev = bs["single"]
            cands.append({"case": None, "single": s,
                          "source": f"beer_scan/{src}", "evidence": ev})
        # adapter mới (websosanh, sendo, shopee...)
        for rs in raw_sources.get(pid, []):
            cands.append(rs)
        # các kênh đã lưu trước đây (tiki, lotte, websosanh...)
        for ch, cv in (prod.get("channels") or {}).items():
            cands.append({"case": cv.get("case_vnd"), "single": cv.get("single_vnd"),
                          "source": ch, "evidence": ""})
        result[pid] = cands
    return result, by_pid, skipped


def decide(pid, cands, old):
    """Quyết định giá case cho 1 product. Trả (case, single, confidence, flags, sources)."""
    flags, sources = [], []
    case_vals = [(c["case"], c["source"]) for c in cands if c.get("case")]
    single_vals = [(c["single"], c["source"]) for c in cands if c.get("single")]

    def pick(vals):
        """Chọn giá từ list (value, source). Trả (value, conf, srcs, conflict)."""
        vals = filter_outliers([v for v in vals if v[0]])
        if not vals:
            return None, None, [], False
        if len(vals) == 1:
            return vals[0][0], "medium", [vals[0][1]], False
        vs = sorted(v[0] for v in vals)
        med = statistics.median(vs)
        lo, hi = vs[0], vs[-1]
        if lo and (hi - lo) / lo > CONFLICT_PCT:
            return None, None, [s for _, s in vals], True  # conflict
        agree = all(abs(v - med) / med <= AGREE_PCT for v in vs) if med else False
        return int(round(med, -3)), ("high" if agree and len(vals) >= 2 else "medium"), [s for _, s in vals], False

    # Nguồn beer-scan (quét mới, đã map thủ công) tin cậy hơn channels lịch sử
    fresh_case = [(v, s) for v, s in case_vals if s.startswith("beer_scan/")]
    fresh_single = [(v, s) for v, s in single_vals if s.startswith("beer_scan/")]

    case, conf, srcs, conflict = pick(case_vals)
    if conflict:
        flags.append("conflict")
        # conflict giữa các kênh cũ, nhưng nếu có nguồn beer-scan mới thì ưu tiên nó
        if fresh_case:
            case, conf, srcs = fresh_case[0][0], "medium", [fresh_case[0][1]]
            flags.remove("conflict")
            flags.append("fresh_override")
        else:
            case = old.get("price_case_vnd")
            conf = old.get("confidence", "low")
    single, sconf, ssrc, sconflict = pick(single_vals)
    if sconflict:
        if fresh_single:
            single, ssrc = fresh_single[0][0], [fresh_single[0][1]]
        else:
            flags.append("conflict")
            single = old.get("price_single_vnd")
    sources = sorted(set(srcs + ssrc))

    # anomaly: so với giá cũ
    old_case = old.get("price_case_vnd")
    if case and old_case and abs(case - old_case) / old_case > ANOMALY_PCT:
        flags.append("anomaly")
    if case and not single:
        single = round(case / 24 / 1000) * 1000
    return case, single, conf or old.get("confidence", "medium"), flags, sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    prices_doc = json.loads((MASTER / "prices_real.json").read_text(encoding="utf-8"))
    cands, by_pid, skipped = collect_candidates(prices_doc)
    today = datetime.date.today().isoformat()

    changed, conflicts, anomalies, touched = [], [], [], 0
    for pid, clist in cands.items():
        prod = by_pid[pid]
        case, single, conf, flags, sources = decide(pid, clist, prod)
        if case is None and single is None:
            continue
        touched += 1
        old_case = prod.get("price_case_vnd")
        if case and case != old_case:
            changed.append((pid, prod.get("name"), old_case, case, conf))
        prod["price_case_vnd"] = case or prod.get("price_case_vnd")
        prod["price_single_vnd"] = single or prod.get("price_single_vnd")
        prod["confidence"] = conf
        prod["captured_date"] = today
        prod["source"] = "+".join(sources) if sources else prod.get("source")
        # ghi channels mới từ beer_scan
        chans = prod.setdefault("channels", {})
        for c in clist:
            src = c["source"].split("/")[-1]
            if c.get("case") or c.get("single"):
                chans[src] = {"case_vnd": c.get("case"), "single_vnd": c.get("single"),
                              "confidence": "medium", "captured_date": today}
        if "conflict" in flags:
            conflicts.append((pid, prod.get("name"), sources))
        if "anomaly" in flags:
            anomalies.append((pid, prod.get("name"), old_case, case))
        if flags:
            prod["flags"] = sorted(set((prod.get("flags") or []) + flags))
        elif prod.get("flags"):
            prod.pop("flags")

    prices_doc["meta"]["captured_date"] = today
    prices_doc["meta"]["reconciled"] = True

    report = {
        "date": today, "touched": touched, "changed": len(changed),
        "conflicts": len(conflicts), "anomalies": len(anomalies),
        "skipped_unmapped": len(skipped),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if changed:
        print("\n-- GIÁ THAY ĐỔI --")
        for pid, name, o, n, cf in changed:
            print(f"  {pid:10s} {name[:35]:35s} {o or '-':>9} -> {n:>9,} [{cf}]")
    if conflicts:
        print("\n-- CONFLICT (giữ giá cũ, cần duyệt) --")
        for pid, name, srcs in conflicts:
            print(f"  {pid:10s} {name[:35]:35s} nguồn: {', '.join(srcs)}")
    if anomalies:
        print("\n-- ANOMALY (biến động >30%) --")
        for pid, name, o, n in anomalies:
            print(f"  {pid:10s} {name[:35]:35s} {o} -> {n}")

    if not args.dry_run:
        (MASTER / "prices_real.json").write_text(
            json.dumps(prices_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        (DYNAMIC / "last_reconcile.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n✅ Đã ghi knowledge/master/prices_real.json")
    else:
        print("\n(dry-run — không ghi file)")


if __name__ == "__main__":
    main()
