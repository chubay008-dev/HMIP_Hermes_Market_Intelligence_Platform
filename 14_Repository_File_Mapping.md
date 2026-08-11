# HMIP — Repository / File Mapping

## 1. Mục tiêu

Tài liệu này ánh xạ rõ ràng giữa repository structure, module responsibility, class responsibility và file placement trong HMIP. Mục tiêu là giúp Claude sinh code đúng vị trí, đúng layer, đúng boundary, tránh nhét logic sai chỗ.

## 2. Mapping principles

- Core runtime nằm trong `core/`.
- Business logic nằm trong `domains/`.
- Ontology và knowledge nằm trong `knowledge/`.
- Bootstrap và diagnostics nằm trong `platform/`.
- Tests phải mirror theo structure hợp lý.
- File nào có responsibility rõ ràng thì chỉ nên mang trách nhiệm đó.

## 3. Repository root structure

```text
HMIP/
├── core/
├── domains/
├── shared/
├── knowledge/
├── playbooks/
├── config/
├── data/
├── reports/
├── tests/
├── deployment/
└── platform/
```

## 4. Core mapping

### `core/context.py`
- `ExecutionContext`
- `ExecutionContextFactory`

### `core/models.py`
- `TaskExecutionResult`
- `BootstrapReport`
- `DecisionResult` nếu dùng chung

### `core/bootstrap.py`
- `BootstrapManager`
- `BootstrapKernel`

### `core/registry.py`
- `TaskRegistry`
- registry state machine

### `core/planner.py`
- `Planner`
- `PipelineDAGExecutor`

### `core/event_bus.py`
- `EventBus` implementation
- publish/subscribe routing

### `core/config.py`
- `ConfigLoader`
- config merge / validate / freeze

### `core/lineage.py`
- `LineageTracer`
- lineage persistence helpers

### `core/validator.py`
- schema validation
- runtime validation helpers

### `core/orchestrator.py`
- Hermes orchestration flow
- execution coordination

### `core/feedback_loop.py`
- human-in-the-loop
- escalation routing

## 5. Domain mapping

### `domains/beer/pricing/models.py`
- `BeerPrice`
- domain-specific DTOs

### `domains/beer/pricing/skills/collect_price.py`
- `ShopeeAdapter` or equivalent adapter implementation
- price collection logic

### `domains/beer/pricing/prompts/extract_price.md`
- extraction prompt for price data

### `domains/beer/pricing/schemas/schema.json`
- validation schema for extracted pricing payload

### `domains/beer/pricing/workflows/WF-PRC-001.yaml`
- PRC-001 workflow definition

### `domains/beer/pricing/decision_engine.py`
- price variance decision logic

### `domains/retail/promo/*`
- promo-related workflow and artifacts

### `domains/pharma/*`
- pharma-related workflow and artifacts

### `domains/competitor/*`
- competitor intelligence workflow and artifacts

## 6. Knowledge mapping

### `knowledge/ontology/core_schema.json`
- Brand
- Product
- SKU

### `knowledge/ontology/models.py`
- ontology entities if implemented as Python models

### `knowledge/master/*`
- master data files

### `knowledge/dynamic/*`
- dynamic intelligence data files

### `knowledge/config/*`
- knowledge-specific config

## 7. Platform mapping

### `platform/bootstrap.py`
- bootstrap entrypoint
- CLI bootstrap command

### `platform/diagnostics.py`
- environment diagnostics
- bootstrap checks

### `platform/registry.py`
- platform-level registry helpers if any
  - only if not conflicting with `core/registry.py`

### `platform/models.py`
- bootstrap-specific models if needed

## 8. Shared mapping

### `shared/constants.py`
- shared constants

### `shared/types.py`
- shared types

### `shared/schemas.py`
- reusable schemas

### `shared/utils.py`
- reusable utility functions

## 9. Config mapping

### `config/runtime.yaml`
- runtime config

### `config/logging.yaml`
- logging config

### `config/deployment.yaml`
- deployment config

### `config/secrets.yaml`
- references only, not plaintext secrets

## 10. Data mapping

### `data/raw/`
- raw external data

### `data/normalized/`
- normalized intermediate data

### `data/validated/`
- schema-validated data

### `data/processed/`
- ready-to-use domain output

## 11. Tests mapping

### `tests/unit/`
- unit tests for core and domain modules

### `tests/integration/`
- integration tests for component boundaries

### `tests/workflow/`
- workflow end-to-end tests

### `tests/prompt/`
- prompt evaluation tests

### `tests/chaos/`
- chaos/fault injection tests

## 12. File placement rules

- Do not place domain business logic inside `core/`.
- Do not place bootstrap/runtime orchestration inside `domains/`.
- Do not place knowledge ontology inside `core/`.
- Do not place config loading logic inside prompt files.
- Do not place implementation code inside Markdown spec files.
- Tests should live under `tests/` and reflect the boundary they verify.

## 13. Example class-to-file mapping

- `ExecutionContext` -> `core/context.py`
- `TaskRegistry` -> `core/registry.py`
- `BootstrapKernel` -> `core/bootstrap.py`
- `PipelineDAGExecutor` -> `core/planner.py`
- `EventBus` -> `core/event_bus.py`
- `BeerPrice` -> `domains/beer/pricing/models.py`
- `LineageTracer` -> `core/lineage.py`
- `WorkflowDefinition` -> `core/workflow/models.py` or split package if needed

## 14. Claude implementation instruction

Khi Claude sinh code cho HMIP:
- tạo file đúng theo mapping này,
- không tự ý đổi location của core/domain/knowledge artifacts,
- nếu cần tách thêm package, phải giữ nguyên boundary,
- bám theo mapping để tránh architecture drift.