# HMIP — Example Workflows

## 1. Mục tiêu

Tài liệu này cung cấp các workflow mẫu để Claude hoặc team engineering tham chiếu khi implement workflow engine, planner, adapter và decision engine. Các ví dụ này không phải implementation code, mà là mô tả chuẩn hóa của execution flow.

## 2. Workflow example: PRC-001 Daily Beer Price Collection

### 2.1. Purpose
Thu thập giá bia hằng ngày từ nguồn external, chuẩn hóa dữ liệu, kiểm tra schema, so sánh với ngưỡng và đưa ra quyết định.

### 2.2. High-level flow
1. Collect raw price payload.
2. Extract structured fields.
3. Validate schema.
4. Compare với base price hoặc policy threshold.
5. Decide.
6. Alert hoặc escalate nếu cần.

### 2.3. Workflow steps

#### Step `collect`
- Input: product_id, source, market
- Output: raw payload
- Responsibility: adapter call
- Failure modes: timeout, network error, source unavailable

#### Step `extract`
- Input: raw payload
- Output: structured JSON
- Responsibility: prompt / extraction logic
- Failure modes: invalid extraction, malformed output

#### Step `validate`
- Input: structured JSON
- Output: validated record
- Responsibility: schema validation
- Failure modes: schema mismatch, missing required field

#### Step `compare`
- Input: validated price and reference price
- Output: variance result
- Responsibility: comparison logic
- Failure modes: invalid base price, inconsistent currency

#### Step `decide`
- Input: variance result
- Output: decision result
- Responsibility: decision engine
- Failure modes: threshold ambiguity, low confidence

#### Step `alert`
- Input: alert-worthy result
- Output: notification or escalation record
- Responsibility: alerting / human review
- Failure modes: notification failure, queue failure

## 3. Workflow example: PRC-002 Price Anomaly Decision

### Purpose
Đánh giá biến động giá đáng ngờ và đưa ra quyết định escalation hoặc alert.

### High-level flow
1. Load validated price events.
2. Calculate deviation.
3. Apply policy thresholds.
4. Return decision.
5. Route to human review if needed.

## 4. Workflow example: PRM-001 Campaign Tracking

### Purpose
Theo dõi campaign/promo data và chuẩn hóa cho analysis.

### High-level flow
1. Collect promo data.
2. Extract fields.
3. Validate schema.
4. Persist normalized promo record.
5. Emit tracking signal.

## 5. Workflow example: CMP-001 Competitor Watch

### Purpose
Theo dõi sản phẩm đối thủ, map SKU, và phát hiện thay đổi đáng chú ý.

### High-level flow
1. Collect competitor source.
2. Extract product data.
3. Match SKU.
4. Validate normalization.
5. Emit competitor signal.

## 6. Workflow rules

- Workflow phải express được thành DAG nếu có dependency.
- Workflow phải có input/output contract.
- Workflow phải có failure mode rõ ràng.
- Workflow không được chứa business logic không thuộc trách nhiệm của nó.

## 7. Claude implementation instruction

Khi Claude triển khai workflow:
- giữ workflow ở mức contract and flow,
- không nhét implementation chi tiết vào spec,
- luôn kèm test tương ứng,
- cập nhật traceability matrix nếu workflow mới xuất hiện.