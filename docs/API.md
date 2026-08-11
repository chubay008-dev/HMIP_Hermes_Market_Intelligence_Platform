# API — HMIP

## Kết luận

`[VERIFIED]` **Không có HTTP API.**

Bằng chứng:
- Không có FastAPI/Flask/Django/uvicorn trong dependencies.
- Không có route decorator, không có OpenAPI/Swagger spec trong repo.
- `docker-compose.yml` **không expose port nào** — comment ghi rõ: *"there is no exposed port"*.
- `job.yaml` không có `containerPort`, không có Service manifest.
- Health/readiness là **exec CLI check**, không phải HTTP endpoint — `health.py` docstring nêu rõ lý do.

Theo mục 16 của workflow: *"Không mô tả endpoint nếu không tìm thấy evidence."* Do đó không có endpoint nào được liệt kê.

## Bề mặt "API" thực tế: CLI

| Lệnh | Handler | Input | Output | Exit code |
|---|---|---|---|---|
| `python -m platform_.bootstrap` | `platform_/bootstrap.py:main` | env vars + `config/*.yaml` | stdout summary + `reports/*.json` | 0 / 1 |
| `python -m platform_.health` | `platform_/health.py:main` | — | `HEALTHY` \| `UNHEALTHY` | 0 / 1 |
| `python -m platform_.readiness` | `platform_/readiness.py:main` | `HMIP_READY_FILE` | `READY` \| `NOT_READY` | 0 / 1 |

## Programmatic API (Python, dùng nội bộ)

`WorkflowEngine` — contract khoá theo `05_Interface_Contract.md` section 4.3:

```python
load(workflow_id: str) -> dict[str, Any]
execute(workflow: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]
cancel(execution_id: str) -> None
```

`[VERIFIED]` `core/workflow_engine.py` L98, L110, L285.

Diễn giải quan trọng (docstring tự nêu, vì contract chỉ nói `dict[str, Any]`): tham số `context` của `execute()` là **business input** (ví dụ `{"product_id": "P123"}`), **không phải** `ExecutionContext` serialize. Engine tự tạo `ExecutionContext` riêng cho tracing.

### Shape trả về của `execute()`

`[VERIFIED]` `workflow_engine.py` L203-214:

| Field | Kiểu | Ghi chú |
|---|---|---|
| `execution_id` | str | uuid4 sinh bên trong |
| `workflow_id` | str | |
| `status` | str | `COMPLETED` \| `FAILED` \| `CANCELLED` |
| `started_at` / `ended_at` | float | epoch |
| `input` | dict | chính là `context` truyền vào |
| `output` | Any | output của task cuối, **chỉ khi COMPLETED**, ngược lại `None` |
| `error` | str \| None | |
| `trace_id` | str | |
| `compensation` | dict | `{triggered, completed, errors[]}` |

### Ngoại lệ có thể raise

| Exception | Khi nào |
|---|---|
| `WorkflowParseException` | workflow sai cấu trúc, id không khớp, có chu trình |
| `WorkflowExecutionException` | lineage write lỗi, event delivery lỗi (lỗi hạ tầng) |

Lỗi nghiệp vụ của task **không raise** — báo qua `status`/`error` trong dict trả về.
