# MODULES — HMIP

## core/ — runtime kernel

**Purpose:** Chỉ chứa mối quan tâm runtime. Không có business logic domain.
**Dependencies:** `pyyaml`, `structlog`, `shared/`
**Consumers:** `platform_/`, `domains/`, `knowledge/`
**Ràng buộc đã xác minh:** `core/` **không import** `domains/` ở bất kỳ đâu — `[VERIFIED]` grep.

| File | Symbol chính | Ghi chú |
|---|---|---|
| `bootstrap.py` | `BootstrapKernel`, `BootstrapManager` | 8 bước; mỗi bước → `TaskExecutionResult` |
| `config.py` | `ConfigLoader`, `FrozenConfig` | load/merge/validate/freeze tách rời |
| `context.py` | `ExecutionContext`, `ExecutionContextFactory` | frozen dataclass đúng 6 field, khoá theo contract |
| `registry.py` | `TaskRegistry`, `RegistryState` | state machine + RLock |
| `planner.py` | `Planner`, `_build_waves` | Kahn's algorithm |
| `executor.py` | `TaskExecutor`, `TaskHandler` | retry + template resolution |
| `workflow.py` | `WorkflowDefinition`, `TaskDefinition`, `RetryPolicy`, `WorkflowLoader` | validate cấu trúc, KHÔNG phát hiện chu trình |
| `workflow_engine.py` | `WorkflowEngine` | tuần tự wave + compensation |
| `event_bus.py` | `EventBus` | pub/sub đồng bộ, thread-safe |
| `lineage.py` | `InMemoryLineageTracer`, `PersistentLineageTracer`, `LineageRecord` | JSONL append-only |
| `models.py` | `TaskExecutionResult`, `BootstrapReport`, `DecisionResult`, enums | shape bị khoá |
| `observability.py` | `configure_logging`, `get_logger`, `log_event` | structlog JSON |
| `exceptions.py` | 8 lớp exception | phân biệt bằng `.code`, không subclass |

## platform_/ — entrypoints

**Purpose:** CLI + health/readiness. Không business logic.
**Tên package:** đổi từ `platform/` (đụng stdlib, làm gãy pytest collection) → `platform_/`. `ADR_010`.
**External interactions:** ghi `reports/*.json`, ghi marker file.

| File | Symbol | Vai trò |
|---|---|---|
| `bootstrap.py` | `main()`, `_register_demo_tasks` | entrypoint container |
| `health.py` | `check_health()`, `main()` | liveness |
| `readiness.py` | `mark_ready()`, `check_readiness()`, `clear_ready()` | readiness marker |
| `diagnostics.py` | `check_python_version()`, `run_diagnostics()` | chỉ 1 check |

## domains/beer/pricing/ — PRC-001

**Purpose:** Vertical slice duy nhất. Thu thập → phân tích → quyết định giá bia.
**Dependencies:** `core/`, `knowledge/`
**Consumers:** chỉ `tests/` — `[VERIFIED]` F-01.

| File | Symbol | Vai trò |
|---|---|---|
| `registrar.py` | `register_prc_001_tasks` | đăng ký 7 handler + 7 rollback |
| `decision_engine.py` | `PricingDecisionEngine` | ngưỡng 5%/10%, confidence 0.7 |
| `models.py` | `BeerPrice` | 12 field, validate trong `__post_init__` |
| `skills/collect_price.py` | `CollectPriceAdapter` | mock, 1 bản ghi |
| `skills/extract_price.py` | `ExtractPriceSkill` | parser tất định (thay cho LLM) |
| `skills/validate_price.py` | — | jsonschema |
| `skills/enrich_price.py` | `enrich_with_ontology` | **nơi duy nhất** dùng ontology |
| `skills/compare_price.py` | `compute_variance` | thuần transform |
| `skills/alert_price.py` | — | trả dict, không gửi thật |

## knowledge/ — ontology layer

**Purpose:** Nguồn sự thật về Brand/Product/SKU.
**Quan hệ:** `Product.brand_id → Brand.id`; `SKU.product_id → Product.id`.
**Phân chia trách nhiệm:** shape từng entity validate trong dataclass `__post_init__`; referential integrity toàn dataset validate ở `loader.load_dataset()` — cùng mô hình với `WorkflowDefinition`.
**Consumers:** chỉ `enrich_price.py`.

## shared/

`constants.py` — `RUNTIME_VERSION` (lấy động từ package metadata, fallback "0.1.0"), `KERNEL_VERSION = "1.0.0"`, hằng số decision.
`types.py` — `JSONObject`, `JSONValue`. **Coverage 0%** — chỉ là type alias, không có runtime code.
