# HMIP — Data Contract

## 1. Mục tiêu

Tài liệu này quy định các data contract cốt lõi của HMIP. Mục tiêu là chuẩn hóa cấu trúc dữ liệu runtime, workflow, domain, knowledge và lineage để Claude có thể sinh model, schema, validation rules và test fixture nhất quán.

## 2. Design principles

- Data contract phải rõ ràng, versioned và testable.
- Mỗi contract phải có trách nhiệm đơn nhất.
- Ưu tiên immutable data structures cho contract quan trọng.
- Schema phải đủ chặt để sinh JSON Schema, Pydantic hoặc dataclass.
- Không trộn runtime metadata vào domain data nếu không cần thiết.

## 3. Common conventions

### 3.1. Identifier fields
- Dùng `str` cho các ID như `execution_id`, `workflow_id`, `task_id`, `brand_id`, `product_id`, `sku_id`.
- ID phải unique trong phạm vi contract.

### 3.2. Time fields
- Dùng ISO 8601 string nếu dùng text representation.
- Nếu dùng numeric timestamp, phải ghi rõ đơn vị là seconds.
- Không trộn nhiều kiểu thời gian trong cùng một contract nếu tránh được.

### 3.3. Enum fields
- Enum-like fields phải có giá trị hợp lệ được chốt trước.
- Không dùng string mơ hồ cho status/decision/severity.

### 3.4. Optional fields
- Optional field phải ghi rõ `| None`.
- Nếu phân biệt missing và null là cần thiết, phải nói rõ trong contract.

## 4. Runtime data contracts

### 4.1. ExecutionContext

```json
{
  "execution_id": "EXEC-ABC12345",
  "trace_id": "2f3c2a98-9f0e-4f6c-a7ea-4fa9c1e1e111",
  "correlation_id": "2f3c2a98-9f0e-4f6c-a7ea-4fa9c1e1e111",
  "epoch": 1,
  "timestamp": 1710000000.0,
  "metadata": {
    "kernel_version": "RC2.1",
    "runtime_version": "1.6.1"
  }
}
```

Fields:
- `execution_id: str`
- `trace_id: str`
- `correlation_id: str`
- `epoch: int`
- `timestamp: float`
- `metadata: dict[str, Any]`

Rules:
- execution_id phải unique.
- trace_id phải đủ để theo dõi execution xuyên suốt.
- metadata phải structured và không nên là raw string blob.

---

### 4.2. TaskExecutionResult

```json
{
  "task_name": "collect",
  "status": "SUCCESS",
  "duration_ms": 123.4,
  "error": null
}
```

Fields:
- `task_name: str`
- `status: str`
- `duration_ms: float`
- `error: str | None`

Allowed status values:
- `SUCCESS`
- `FAILED`
- `SKIPPED`
- `RETRYING`
- `CANCELLED`

---

### 4.3. BootstrapReport

```json
{
  "execution_id": "EXEC-ABC12345",
  "status": "SUCCESS",
  "task_results": [],
  "runtime_version": "1.6.1",
  "kernel_version": "RC2.1"
}
```

Fields:
- `execution_id: str`
- `status: str`
- `task_results: list[TaskExecutionResult]` hoặc `tuple[TaskExecutionResult, ...]`
- `runtime_version: str`
- `kernel_version: str`

Allowed status values:
- `SUCCESS`
- `FAILED`
- `PARTIAL`

Rules:
- task_results phải phản ánh toàn bộ bootstrap steps đã chạy.
- status phải tương thích với aggregate outcome.

---

### 4.4. WorkflowExecutionRecord

```json
{
  "execution_id": "EXEC-ABC12345",
  "workflow_id": "WF-PRC-001",
  "status": "COMPLETED",
  "started_at": "2026-07-31T10:00:00Z",
  "ended_at": "2026-07-31T10:00:12Z",
  "input": {
    "product_id": "P123",
    "source": "shopee",
    "market": "VN"
  },
  "output": {
    "decision": "ALERT"
  },
  "error": null,
  "trace_id": "2f3c2a98-9f0e-4f6c-a7ea-4fa9c1e1e111"
}
```

Fields:
- `execution_id: str`
- `workflow_id: str`
- `status: str`
- `started_at: str | None`
- `ended_at: str | None`
- `input: dict[str, Any]`
- `output: dict[str, Any] | None`
- `error: str | None`
- `trace_id: str`

Allowed status values:
- `STARTED`
- `RUNNING`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

## 5. Workflow data contracts

### 5.1. WorkflowDefinition

```json
{
  "id": "WF-PRC-001",
  "version": "1.1.0",
  "owner": "Pricing Team",
  "status": "PRODUCTION",
  "risk": "MEDIUM",
  "tasks": [],
  "inputs": [],
  "outputs": [],
  "retry_policy": "exponential_backoff",
  "compensation_policy": "STRICT",
  "schema_dependencies": ["schema.json"],
  "prompt_dependencies": ["extract_price.md"],
  "skill_dependencies": ["beer.pricing.collect_price"]
}
```

Fields:
- `id: str`
- `version: str`
- `owner: str`
- `status: str`
- `risk: str`
- `tasks: list[dict[str, Any]]`
- `inputs: list[str]`
- `outputs: list[str]`
- `retry_policy: str | dict[str, Any]`
- `compensation_policy: str`
- `schema_dependencies: list[str]`
- `prompt_dependencies: list[str]`
- `skill_dependencies: list[str]`

---

### 5.2. TaskDefinition

```json
{
  "id": "collect",
  "type": "adapter",
  "input": {
    "product_id": "P123",
    "source": "shopee"
  },
  "output": "${collect.output}",
  "dependencies": [],
  "retry_policy": "exponential_backoff",
  "timeout": 30,
  "failure_modes": ["timeout", "network_error", "parse_error"]
}
```

Fields:
- `id: str`
- `type: str`
- `input: dict[str, Any] | Any`
- `output: dict[str, Any] | Any`
- `dependencies: list[str]`
- `retry_policy: str | dict[str, Any]`
- `timeout: int`
- `failure_modes: list[str]`

Allowed type values:
- `adapter`
- `prompt`
- `schema_validate`
- `decision`
- `notify`
- `transform`
- `persist`

---

### 5.3. DecisionResult

```json
{
  "decision": "ALERT",
  "confidence": 0.87,
  "reason": "price variance > 10%",
  "recommended_action": "notify_pricing_team"
}
```

Fields:
- `decision: str`
- `confidence: float`
- `reason: str`
- `recommended_action: str | None`

Allowed decision values:
- `IGNORE`
- `ALERT`
- `ESCALATE`
- `HUMAN_REVIEW`

Rules:
- confidence phải nằm trong khoảng `0.0` đến `1.0`.
- decision phải thuộc allowed values.
- reason phải đủ để audit.

## 6. Domain data contracts

### 6.1. BeerPrice

```json
{
  "product_id": "P123",
  "sku": "SKU-001",
  "brand": "Saigon Beer",
  "product_name": "Saigon Special 330ml",
  "price": 18500.0,
  "currency": "VND",
  "store": "Shopee",
  "province": "HCMC",
  "capture_time": "2026-07-31T10:00:00Z",
  "confidence": 0.93,
  "source_url": "https://example.com/product/123",
  "source": "shopee"
}
```

Fields:
- `product_id: str`
- `sku: str | None`
- `brand: str`
- `product_name: str`
- `price: float`
- `currency: str`
- `store: str`
- `province: str | None`
- `capture_time: str`
- `confidence: float`
- `source_url: str`
- `source: str`

Rules:
- price > 0
- confidence trong khoảng 0.0..1.0
- capture_time phải rõ đơn vị hoặc ISO 8601
- currency phải theo quy ước project

---

### 6.2. CompetitorProduct

```json
{
  "competitor_id": "COMP-001",
  "product_name": "Heineken Silver 330ml",
  "brand": "Heineken",
  "category": "Beer",
  "price": 21000.0,
  "currency": "VND",
  "source_url": "https://example.com/comp/1",
  "observed_at": "2026-07-31T10:00:00Z"
}
```

Fields:
- `competitor_id: str`
- `product_name: str`
- `brand: str`
- `category: str`
- `price: float | None`
- `currency: str | None`
- `source_url: str | None`
- `observed_at: str`

---

### 6.3. MarketSignal

```json
{
  "signal_id": "SIG-001",
  "signal_type": "PRICE_CHANGE",
  "source": "workflow",
  "severity": "HIGH",
  "payload": {
    "product_id": "P123",
    "delta_percent": 12.5
  },
  "created_at": "2026-07-31T10:00:12Z"
}
```

Fields:
- `signal_id: str`
- `signal_type: str`
- `source: str`
- `severity: str`
- `payload: dict[str, Any]`
- `created_at: str`

Allowed severity values:
- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

## 7. Knowledge data contracts

### 7.1. Brand

```json
{
  "brand_id": "BR-001",
  "name": "Saigon Beer",
  "origin": "Vietnam",
  "tier": "premium"
}
```

Fields:
- `brand_id: str`
- `name: str`
- `origin: str | None`
- `tier: str | None`

---

### 7.2. Product

```json
{
  "product_id": "PRD-001",
  "brand_id": "BR-001",
  "category_id": "CAT-BEER",
  "is_active": true
}
```

Fields:
- `product_id: str`
- `brand_id: str`
- `category_id: str | None`
- `is_active: bool`

---

### 7.3. SKU

```json
{
  "sku_id": "SKU-001",
  "product_id": "PRD-001",
  "volume": "330ml",
  "package_type": "can",
  "barcode": "893850000001"
}
```

Fields:
- `sku_id: str`
- `product_id: str`
- `volume: str | None`
- `package_type: str | None`
- `barcode: str | None`

## 8. Lineage data contracts

### 8.1. LineageRecord

```json
{
  "step": "extract",
  "input_value": "raw payload",
  "output_value": {
    "product_name": "Saigon Special 330ml",
    "price": 18500.0
  },
  "model_info": "prompt:extract_price.md v1.0.2",
  "timestamp": 1710000012.0,
  "integrity_hash": "sha256:abc123..."
}
```

Fields:
- `step: str`
- `input_value: Any`
- `output_value: Any`
- `model_info: str`
- `timestamp: float`
- `integrity_hash: str`

Rules:
- trace record phải có bước rõ ràng.
- hash phải tính trên canonical output.
- không ghi secret plaintext.

---

### 8.2. ProvenanceRecord

```json
{
  "source_id": "shopee",
  "source_type": "external",
  "captured_at": "2026-07-31T10:00:00Z",
  "resolution_chain": "raw -> extracted -> validated -> decision",
  "trace_id": "2f3c2a98-9f0e-4f6c-a7ea-4fa9c1e1e111"
}
```

Fields:
- `source_id: str`
- `source_type: str`
- `captured_at: str`
- `resolution_chain: str`
- `trace_id: str`

## 9. Validation rules

- Không nhận payload thiếu required fields.
- Không cho giá âm trong pricing domain.
- Không cho confidence ngoài khoảng `0..1`.
- Không cho workflow/task contract thiếu id.
- Không cho lineage thiếu step hoặc hash.
- Không cho execution record thiếu trace context.

## 10. Serialization rules

- Tất cả schema phải serialize được sang JSON.
- Nếu dùng YAML workflow, dữ liệu phải parse được sang schema tương ứng.
- Datetime nên dùng ISO 8601 nếu không dùng native datetime object.
- Immutable contracts nên dùng `dataclass(frozen=True)` hoặc `pydantic.BaseModel`.

## 11. Mapping to implementation

Khuyến nghị mapping:
- `ExecutionContext` -> `core/context.py`
- `TaskExecutionResult` -> `core/models.py`
- `BootstrapReport` -> `core/models.py`
- `DecisionResult` -> `domains/beer/pricing/models.py` hoặc `core/models.py` nếu dùng chung
- `LineageRecord` -> `core/lineage/models.py`
- `BeerPrice` -> `domains/beer/pricing/models.py`
- `WorkflowDefinition` -> `core/workflow/models.py`
- `TaskDefinition` -> `core/workflow/models.py`
- `WorkflowExecutionRecord` -> `core/workflow/models.py`
- `Brand/Product/SKU` -> `knowledge/ontology/models.py`

## 12. Claude implementation instruction

Khi Claude sinh code từ data contract này:
- ưu tiên immutable models cho contract quan trọng,
- sinh Pydantic hoặc dataclass có validation,
- không thêm field ngoài spec nếu chưa có yêu cầu,
- giữ naming đúng chuẩn,
- viết test cho validation, serialization và edge cases.