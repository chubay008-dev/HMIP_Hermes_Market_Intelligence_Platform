# DATA_FLOW — HMIP

## Flow 1 — Bootstrap (đồng bộ, LÀ flow duy nhất chạy thật trong production)

```text
python -m platform_.bootstrap
        ↓
_config_paths()  →  [config/runtime.yaml, logging.yaml, deployment.yaml]
        ↓
BootstrapKernel.run()
        ↓
  1 load_environment    (kiểm tra config_paths không rỗng)
  2 resolve_config      ConfigLoader: read → merge → expand ${VAR} → secrets(stub) → validate → freeze
  3 initialize_logging  configure_logging()  ← không truyền level, xem F-04
  4 initialize_registry (no-op, registry đã tạo ở __init__)
  5 register_tasks      task_registrar(registry)
  6 freeze_registry     READY → FROZEN
  7 build_context       ExecutionContextFactory.create()
  8 validate_runtime    kiểm tra config + context không None
        ↓
BootstrapReport(execution_id, status, task_results[8])
        ↓
   ├→ reports/bootstrap_<uuid>.json
   ├→ log JSON có cấu trúc (structlog)
   └→ mark_ready()  (chỉ khi SUCCESS)
        ↓
   exit 0 | 1
```

Fail-fast: bước nào FAILED thì dừng vòng lặp ngay (`bootstrap.py` L115-119), nhưng report **vẫn được ghi** để debug được điểm hỏng.

## Flow 2 — Workflow execution (đồng bộ; hiện chỉ chạy trong test)

```text
business input {product_id, source, market}
        ↓
WorkflowEngine.execute(workflow_dict, context)
        ↓
outputs = dict(context)          ← seed, cho phép "${product_id}" resolve được
        ↓
WorkflowLoader.loads()           validate cấu trúc  → WorkflowParseException nếu sai
        ↓
Planner.plan()                   waves = [[collect],[extract],...]  → chu trình = raise
        ↓
TaskRegistry mới → registrar() → freeze() → EXECUTING
        ↓
   ┌── với từng task_id theo thứ tự phẳng ──┐
   │  kiểm tra cancelled?  → CANCELLED, break│
   │  TaskExecutor.execute()                 │
   │     ├ resolve "${...}" từ outputs       │
   │     ├ gọi handler (retry theo policy)   │
   │     └ outputs[task_id] = output         │
   │  LineageTracer.record_trace()  ← lỗi ⇒ raise WorkflowExecutionException
   │  EventBus.publish(task_completed) ← lỗi ⇒ raise WorkflowExecutionException
   │  nếu không SUCCESS → status=FAILED, break│
   └─────────────────────────────────────────┘
        ↓
   FAILED + STRICT?  →  _compensate()  (ngược thứ tự, gom lỗi)
        ↓
registry → COMPLETED | FAILED
        ↓
return {execution_id, workflow_id, status, started_at, ended_at,
        input, output, error, trace_id, compensation}
```

## Flow 3 — Dữ liệu PRC-001 biến đổi qua từng bước

```text
{product_id: "P123", source: "shopee", market: "VN"}
        ↓ collect  (CollectPriceAdapter — mock dict)
{brand: "Saigon Beer", product_name: "Saigon Special 330ml",
 price_text: "18,500", currency: "VND", store: "Shopee",
 province: "HCMC", source_url: ..., product_id, source, fetched_at}
        ↓ extract  ("18,500" → 18500.0; fetched_at → ISO capture_time)
{product_id, sku: None, brand, product_name, price: 18500.0,
 currency, store, province, capture_time, confidence: 0.9, source_url, source}
        ↓ validate (jsonschema — không đổi dữ liệu)
        ↓ enrich   (đối chiếu ontology: product phải tồn tại, brand phải khớp; điền sku)
{... sku: "<từ ontology>" ...}
        ↓ compare  (base_price = 18000.0)
{current_price: 18500.0, base_price: 18000.0, delta: 500.0,
 delta_percent: 2.78, confidence: 0.9}
        ↓ decide   (2.78% < 5%, confidence 0.9 >= 0.7)
{decision: "IGNORE", confidence: 0.9, reason: "price variance 2.8% vs base 18000.0",
 recommended_action: None}
        ↓ alert    (IGNORE ⇒ không thông báo)
{notified: False, decision: "IGNORE"}
```

`[VERIFIED]` — số liệu suy ra từ hằng số thật trong source: `_MOCK_SOURCE_DATA["price_text"] = "18,500"` (`collect_price.py` L30), `DEFAULT_BASE_PRICE = 18000.0` (`registrar.py` L47), ngưỡng 5/10% (`decision_engine.py` L28-29).

## Flow 4 — Compensation (chỉ khi FAILED + STRICT)

```text
task N thất bại
        ↓
duyệt NGƯỢC executed_task_ids  (N-1, N-2, ... 0)
        ↓
với từng task: registry.get_task(id)["rollback"]
        ├ không callable  → bỏ qua (không tính lỗi)
        └ callable        → gọi rollback({task_id, output, execution_id})
                               ├ ok    → ghi lineage "rollback:<id>" (best-effort)
                               └ lỗi   → gom vào errors[], TIẾP TỤC task kế
        ↓
{triggered: True, completed: len(errors)==0, errors: [...]}
```

## Phân loại flow

| Loại | Có trong hệ thống? |
|---|---|
| Synchronous | **Có** — toàn bộ hệ thống |
| Asynchronous | Không — không async/await, không thread pool `[VERIFIED]` |
| Event-driven | **Một phần** — `EventBus` tồn tại nhưng handler được gọi đồng bộ ngay trong vòng lặp; không có subscriber nào được đăng ký ngoài test |
| Scheduled | Không trong repo — `job.yaml` gợi ý bọc CronJob nhưng chưa có manifest |
