# HMIP — Traceability Matrix

## 1. Mục tiêu

Tài liệu này ánh xạ từ capability nghiệp vụ xuống workflow, skill, prompt, schema và test. Mục tiêu là đảm bảo mọi capability có thể truy vết rõ ràng từ business goal đến implementation artifact.

## 2. Traceability principles

- Mỗi capability phải có workflow tương ứng.
- Mỗi workflow phải có artifact đi kèm.
- Mỗi artifact phải có test tương ứng.
- Không để capability tồn tại mà không thể truy vết đến implementation.

## 3. Matrix

| Capability ID | Event | Workflow | Skill | Prompt | Schema | Test |
|---|---|---|---|---|---|---|
| CAP-PRC-01 | EVT_PRICE_CHANGED | WF-PRC-001 | collect_price.py | extract_price.md | schema.json | test_prc_001.py |
| CAP-PRC-02 | EVT_PRICE_ANOMALY | WF-PRC-002 | decision_engine.py | evaluate_anomaly.md | anomaly.json | test_decision.py |
| CAP-PRM-01 | EVT_PROMO_CHANGE | WF-PRM-001 | extract_promo.py | extract_promo.md | promo_schema.json | test_prm_001.py |
| CAP-CMP-01 | EVT_COMPETITOR_UPDATE | WF-CMP-001 | sku_matcher.py | match_sku.md | sku_match_schema.json | test_cmp_001.py |

## 4. Traceability rules

- Một capability chỉ được coi là complete khi workflow, skill, prompt, schema và test đã tồn tại.
- Nếu workflow thay đổi, traceability matrix phải được cập nhật.
- Nếu prompt hoặc schema thay đổi, test liên quan phải được cập nhật.
- Mọi artifact production phải map được về ít nhất một capability.

## 5. Claude implementation instruction

Khi Claude triển khai HMIP:
- luôn kiểm tra traceability trước khi sinh code,
- không tạo artifact mới mà không có row tương ứng,
- nếu thêm workflow, phải thêm row vào matrix,
- nếu thay đổi capability, phải cập nhật matrix trước khi merge.