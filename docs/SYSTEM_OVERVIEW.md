# SYSTEM_OVERVIEW — HMIP

## HMIP là gì

HMIP (Hermes Market Intelligence Platform) là một **runtime kernel điều phối workflow theo DAG**, kèm một domain vertical slice duy nhất: **PRC-001 — thu thập & phân tích giá bia**.

`[VERIFIED]` `pyproject.toml` L4: *"Enterprise AI Operating System, single-agent autonomous runtime"*.

Điểm quan trọng cần nắm ngay:

- Đây **không phải web service**. Không có HTTP server, không có port, không có REST API. `[VERIFIED]` — dependency chỉ có pyyaml/structlog/jsonschema.
- Đây **không có database**. Persistence duy nhất là 2 loại file: report JSON và lineage JSONL. `[VERIFIED]`
- Đây là **CLI chạy-rồi-thoát** (run-to-completion), đóng gói dưới dạng Kubernetes `Job`, không phải `Deployment`. `[VERIFIED]` `deployment/kubernetes/job.yaml`.

## Các thành phần chính

| Tầng | Thư mục | Vai trò |
|---|---|---|
| Kernel | `core/` | bootstrap, config, registry, planner, executor, workflow engine, event bus, lineage, observability |
| Platform | `platform_/` | CLI entrypoint + health/readiness |
| Domain | `domains/beer/pricing/` | 7 task handler của PRC-001 + decision engine |
| Knowledge | `knowledge/` | ontology Brand/Product/SKU + master data JSON |
| Shared | `shared/` | hằng số, type alias |

## Ứng dụng khởi động thế nào

```text
python -m platform_.bootstrap
  → BootstrapKernel.run()  chạy 8 bước tuần tự, fail-fast
  → BootstrapManager       log 1 event có cấu trúc
  → ghi reports/bootstrap_<uuid>.json
  → mark_ready()           tạo marker file (chỉ khi thành công)
  → exit 0
```

`[VERIFIED]` — chạy thật trên máy này: `[HMIP] bootstrap OK — steps=8`, exit 0; `health` → HEALTHY; `readiness` → READY.

8 bước, theo đúng thứ tự trong `core/bootstrap.py:run()` L100-109:
`load_environment → resolve_config → initialize_logging → initialize_registry → register_tasks → freeze_registry → build_context → validate_runtime`

## Request đi qua hệ thống thế nào

Không có "request" theo nghĩa HTTP. Đơn vị công việc là một **workflow execution**:

```text
WorkflowEngine.execute(workflow_dict, business_input)
  → WorkflowLoader.loads()   validate cấu trúc (id trùng, dependency lạ, type hợp lệ)
  → Planner.plan()           dựng sóng (wave) bằng Kahn's algorithm, phát hiện chu trình
  → TaskRegistry             tạo mới + freeze + chuyển sang EXECUTING cho MỖI lần execute
  → với từng task theo thứ tự: TaskExecutor.execute()
       → resolve "${...}" từ dict outputs
       → gọi handler, retry theo RetryPolicy
       → ghi outputs[task_id]
       → LineageTracer.record_trace()
       → EventBus.publish({"event_type": "task_completed", ...})
  → nếu FAILED và compensation_policy == STRICT → chạy rollback ngược thứ tự
  → trả dict WorkflowExecutionRecord
```

`[VERIFIED]` `core/workflow_engine.py:execute` L110-215.

## Database ở đâu

**Không có.** `[VERIFIED]` Hai điểm ghi duy nhất:

1. `reports/bootstrap_<execution_id>.json` — `platform_/bootstrap.py:_write_bootstrap_report` L71-84.
2. `knowledge/dynamic/lineage/lineage.jsonl` — `core/lineage.py:PersistentLineageTracer.DEFAULT_PATH` L128.

Mặc định `WorkflowEngine` dùng `InMemoryLineageTracer` (mất khi thoát process), không phải bản persistent — `core/workflow_engine.py` L79-81.

## External services nào được dùng

**Không có.** `CollectPriceAdapter` trả dữ liệu từ dict hardcode. `[VERIFIED]` `collect_price.py` L25-35.

## Entry point quan trọng

- `platform_/bootstrap.py:main()` — cái duy nhất chạy trong container.
- `core/workflow_engine.py:WorkflowEngine` — **chỉ được gọi từ test**, chưa có entrypoint sản phẩm. Xem `VERIFICATION_REPORT.md` F-01.
