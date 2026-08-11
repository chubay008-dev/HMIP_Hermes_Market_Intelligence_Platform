# HMIP — Project Backlog

## 1. Mục tiêu

Tài liệu này chia nhỏ HMIP thành các sprint, epics, và task cụ thể để Claude hoặc team engineering có thể triển khai theo thứ tự hợp lý. Mục tiêu là tránh code nhảy cóc, giảm phụ thuộc ngầm, và đảm bảo nền tảng được dựng trước khi phát triển vertical slice.

## 2. Backlog principles

- Build core before business.
- Finish contracts before implementation detail.
- Implement one vertical slice end-to-end before adding another.
- Every task must have a definition of done.
- Every task should be testable.
- Every sprint should deliver a runnable increment.

## 3. Epic structure

### Epic A — Core Runtime Foundation
Mục tiêu:
- dựng bootstrap,
- context,
- registry,
- config subsystem,
- basic logging.

### Epic B — Workflow Execution Engine
Mục tiêu:
- planner,
- DAG execution,
- event bus,
- workflow loading,
- task execution flow.

### Epic C — PRC-001 Vertical Slice
Mục tiêu:
- beer pricing collection,
- prompt extraction,
- schema validation,
- decision engine,
- alert/review.

### Epic D — Knowledge & Lineage
Mục tiêu:
- ontology,
- master data,
- dynamic data,
- lineage recording,
- provenance trace.

### Epic E — Testing & Quality
Mục tiêu:
- unit,
- integration,
- workflow,
- prompt evaluation,
- chaos testing.

### Epic F — Deployment & Operations
Mục tiêu:
- containerization,
- bootstrap deployment,
- health/readiness,
- observability,
- release flow.

## 4. Sprint breakdown

### Sprint 1 — Foundation

#### Tasks
- Create repository skeleton.
- Create ExecutionContext model and factory.
- Create TaskRegistry with state machine.
- Create BootstrapManager skeleton.
- Create config loader skeleton.
- Create basic logging setup.
- Create initial tests for context and registry.

#### Definition of Done
- Bootstrap runs successfully.
- Registry state machine works.
- Context is generated uniquely.
- Unit tests pass for foundation modules.

### Sprint 2 — Runtime Core

#### Tasks
- Create event bus abstraction.
- Create planner and DAG executor.
- Implement workflow loading contract.
- Implement task execution contract.
- Add cycle detection.
- Add retry policy skeleton.
- Add integration tests for orchestrator flow.

#### Definition of Done
- Workflow can be parsed and planned.
- DAG execution works for a simple acyclic workflow.
- Dependency failures are handled correctly.
- Integration tests pass.

### Sprint 3 — PRC-001 Vertical Slice

#### Tasks
- Create beer pricing domain structure.
- Implement Shopee adapter or source adapter.
- Implement extract prompt.
- Implement schema validation.
- Implement decision engine.
- Implement workflow YAML.
- Add end-to-end workflow test.

#### Definition of Done
- PRC-001 runs end-to-end.
- Output matches schema.
- Decision engine returns correct result.
- Lineage is recorded.
- Workflow test passes.

### Sprint 4 — Knowledge & Lineage

#### Tasks
- Implement ontology schema.
- Implement master data structure.
- Implement dynamic data structure.
- Implement lineage tracer.
- Implement provenance trace persistence.
- Add tests for lineage and ontology.

#### Definition of Done
- Ontology loads and validates.
- Lineage records are generated correctly.
- Provenance trace is queryable or persistable.
- Tests pass.

### Sprint 5 — Testing & Quality

#### Tasks
- Expand unit test coverage.
- Add workflow regression tests.
- Add prompt evaluation tests.
- Add chaos/fault injection tests.
- Create golden dataset for extraction/decisioning.

#### Definition of Done
- Coverage threshold reached.
- Failure paths tested.
- Prompt outputs stable against golden dataset.
- Chaos tests run successfully.

### Sprint 6 — Deployment & Operations

#### Tasks
- Add Dockerfile.
- Add deployment manifests.
- Add healthcheck and readiness endpoints.
- Add bootstrap CLI command.
- Add observability integration.
- Add release checklist.

#### Definition of Done
- Container builds successfully.
- Bootstrap succeeds in container.
- Health/readiness checks pass.
- Observability works.
- Release process documented.

## 5. Task prioritization rules

- Foundation tasks always come first.
- Runtime core tasks must be complete before vertical slice expansion.
- PRC-001 must be finished before new domains are added.
- Quality tasks must be applied before production deployment.
- Deployment tasks must not be skipped.

## 6. Dependency rules

- No domain workflow should be implemented before context, registry, config, and planner exist.
- No prompt or schema should be considered final before workflow contract is in place.
- No deployment should happen before testing standards are satisfied.
- No additional domain should be added before PRC-001 is stable.

## 7. Claude implementation instruction

Khi Claude triển khai HMIP:
- làm đúng thứ tự backlog,
- không nhảy sang domain khác trước khi PRC-001 xong,
- mỗi task phải có test đi kèm,
- mỗi sprint phải tạo ra increment chạy được,
- không hoàn thành task nếu chưa đạt DoD.