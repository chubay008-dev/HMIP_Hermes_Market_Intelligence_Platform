# HMIP — API Contract

## 1. Mục tiêu

Tài liệu này quy định API contract cốt lõi của HMIP cho bootstrap, health, readiness, workflow execution, registry và observability. Mục tiêu là giúp Claude sinh API nhất quán, versioned, testable và không tự ý suy diễn schema.

## 2. API design principles

- API phải versioned.
- Request/response phải có schema rõ ràng.
- API phải reflect đúng responsibility của runtime, không nhét business logic vào transport layer.
- Endpoint phải nhỏ, rõ và testable.
- Các action mutating phải idempotent nếu có thể, hoặc có idempotency key.
- Không expose secret hoặc data nhạy cảm qua API.

## 3. Base conventions

- Base path: `/api/v1`
- Content-Type: `application/json`
- Error response chuẩn hóa
- Request/response nên có `request_id` và `trace_id` nếu có thể
- Không đổi contract âm thầm

## 4. Common response envelope

### Success
```json
{
  "success": true,
  "data": {},
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

### Error
```json
{
  "success": false,
  "error": {
    "code": "CONFIG_VALIDATION_ERROR",
    "message": "Invalid configuration value",
    "details": {}
  },
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

## 5. Health and readiness endpoints

### 5.1. GET /api/v1/health
Purpose:
- liveness check.

Response example:
```json
{
  "success": true,
  "data": {
    "status": "ok"
  }
}
```

### 5.2. GET /api/v1/ready
Purpose:
- readiness check.

Response example:
```json
{
  "success": true,
  "data": {
    "status": "ready"
  }
}
```

## 6. Bootstrap endpoints

### 6.1. POST /api/v1/bootstrap/run
Purpose:
- kích hoạt bootstrap process.

Request example:
```json
{
  "epoch": 1
}
```

Response example:
```json
{
  "success": true,
  "data": {
    "execution_id": "EXEC-XXXX",
    "status": "SUCCESS"
  }
}
```

### 6.2. GET /api/v1/bootstrap/status
Purpose:
- lấy trạng thái bootstrap gần nhất.

Response example:
```json
{
  "success": true,
  "data": {
    "execution_id": "EXEC-XXXX",
    "status": "SUCCESS",
    "runtime_version": "1.6.1",
    "kernel_version": "RC2.1"
  }
}
```

## 7. Workflow endpoints

### 7.1. POST /api/v1/workflow/run
Purpose:
- kích hoạt workflow execution.

Request example:
```json
{
  "workflow_id": "WF-PRC-001",
  "input": {
    "product_id": "P123",
    "source": "shopee",
    "market": "VN"
  },
  "idempotency_key": "optional-string"
}
```

Response example:
```json
{
  "success": true,
  "data": {
    "execution_id": "EXEC-XXXX",
    "workflow_id": "WF-PRC-001",
    "status": "STARTED"
  }
}
```

### 7.2. GET /api/v1/workflow/{execution_id}
Purpose:
- lấy trạng thái workflow execution.

Response example:
```json
{
  "success": true,
  "data": {
    "execution_id": "EXEC-XXXX",
    "workflow_id": "WF-PRC-001",
    "status": "COMPLETED",
    "started_at": "2026-07-31T10:00:00Z",
    "ended_at": "2026-07-31T10:00:12Z"
  }
}
```

### 7.3. POST /api/v1/workflow/{execution_id}/cancel
Purpose:
- hủy workflow execution nếu policy cho phép.

Response example:
```json
{
  "success": true,
  "data": {
    "execution_id": "EXEC-XXXX",
    "status": "CANCELLED"
  }
}
```

## 8. Registry endpoints

### 8.1. GET /api/v1/registry/state
Purpose:
- trả về lifecycle state của registry.

Response example:
```json
{
  "success": true,
  "data": {
    "state": "FROZEN"
  }
}
```

### 8.2. GET /api/v1/registry/tasks
Purpose:
- liệt kê task đã đăng ký.

Response example:
```json
{
  "success": true,
  "data": {
    "tasks": [
      {
        "name": "collect",
        "state": "READY"
      }
    ]
  }
}
```

## 9. Observability endpoints

### 9.1. GET /api/v1/metrics
Purpose:
- expose metrics nếu implementation hỗ trợ.

### 9.2. GET /api/v1/trace/{trace_id}
Purpose:
- truy xuất trace hoặc lineage nếu backend hỗ trợ.

### 9.3. GET /api/v1/logs/{execution_id}
Purpose:
- lấy bundle log theo execution id nếu có storage phù hợp.

## 10. Error codes

- `BOOTSTRAP_ERROR`
- `CONFIG_VALIDATION_ERROR`
- `REGISTRY_STATE_ERROR`
- `WORKFLOW_PARSE_ERROR`
- `WORKFLOW_EXECUTION_ERROR`
- `VALIDATION_ERROR`
- `DECISION_ENGINE_ERROR`
- `LINEAGE_ERROR`
- `DEPENDENCY_ERROR`
- `PERMISSION_ERROR`

## 11. API versioning rules

- Tất cả endpoint phải nằm dưới versioned base path.
- Breaking change phải tạo version mới.
- Backward-compatible change có thể giữ nguyên version nếu không phá contract.
- Không đổi request/response contract âm thầm.

## 12. Security rules

- Endpoints mutating phải có auth nếu triển khai production.
- Không expose secret hoặc sensitive metadata qua API.
- Logs phải sanitize input/output nếu chứa nhạy cảm.
- Internal endpoint phải có boundary rõ ràng.

## 13. Claude implementation instruction

Khi Claude implement API:
- giữ đúng schema request/response,
- không thêm field ngoài contract nếu chưa có spec mới,
- ưu tiên endpoint nhỏ, rõ, testable,
- tách transport layer khỏi business logic,
- tạo test cho mọi endpoint quan trọng.