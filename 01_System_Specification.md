# HMIP — System Specification

## 1. Mục tiêu

HMIP là một **Enterprise AI Operating System** được thiết kế để vận hành các workflow AI trong môi trường doanh nghiệp theo mô hình **single-agent autonomous**. Hermes Agent là orchestrator trung tâm duy nhất, chịu trách nhiệm điều phối workflow, runtime lifecycle, escalation, và phối hợp với các lớp core, domain, knowledge và operations.

Mục tiêu của HMIP là biến AI từ một tính năng hỗ trợ thành một runtime platform có khả năng điều phối dữ liệu, tri thức, công cụ và quyết định nghiệp vụ một cách nhất quán, có thể kiểm soát và có thể truy vết.

## 2. Scope

HMIP bao gồm 5 lớp chính:

- **Core Runtime**
- **Domain Layer**
- **Knowledge Layer**
- **Platform Layer**
- **Operations Layer**

### 2.1. Core Runtime
Chứa:
- bootstrap
- registry
- execution context
- planner
- event bus
- config subsystem
- validator
- observability
- lineage
- feedback loop
- orchestrator

### 2.2. Domain Layer
Chứa business logic theo vertical slice DDD, ví dụ:
- beer pricing
- retail promo
- pharma intelligence
- competitor watch

### 2.3. Knowledge Layer
Chứa:
- ontology
- master data
- dynamic intelligence
- provenance
- lineage support

### 2.4. Platform Layer
Chứa:
- bootstrap tooling
- diagnostics
- environment bootstrap
- deployment helpers

### 2.5. Operations Layer
Chứa:
- testing
- tracing
- logging
- CI/CD
- deployment
- chaos testing
- operational safeguards

## 3. Architecture Principles

- Single-Agent Autonomous.
- Vertical Slice First.
- Runtime Before Business.
- Immutable by Default.
- Trace Everything.
- Test or It Doesn’t Exist.
- No hidden orchestration logic inside domain code.
- No bypass of validation or policy.
- No business logic in core runtime.

## 4. Runtime Model

### 4.1. Control Plane
Chịu trách nhiệm:
- bootstrap
- registry
- configuration
- policy
- validation

### 4.2. Execution Plane
Chịu trách nhiệm:
- workflow engine
- adapter execution
- prompt execution
- decision engine
- escalation and human review

### 4.3. Observability Plane
Chịu trách nhiệm:
- structured logging
- metrics
- tracing
- lineage capture
- audit support

### 4.4. Core lifecycle
1. Environment load.
2. Config load and resolution.
3. Registry initialization.
4. Task/plugin registration.
5. Registry freeze.
6. Execution context creation.
7. Workflow planning.
8. Workflow execution.
9. Lineage capture.
10. Decision output.
11. Report / alert / escalation.

## 5. Repository Standard

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

### Responsibility
- `core/`: runtime kernel only.
- `domains/`: all business logic.
- `knowledge/`: ontology and intelligence.
- `platform/`: bootstrap and diagnostics.
- `tests/`: all testing.
- `deployment/`: container and CI/CD artifacts.

## 6. System-level rules

- Hermes is the only orchestrator.
- Workflow must be planable as DAG.
- Registry must be frozen after bootstrap.
- Config must be immutable after bootstrap unless explicit reload policy exists.
- Output that matters must have trace and lineage.
- Decision engine must be separated from orchestration.
- Confidence thấp phải route sang human review hoặc escalation.
- Core runtime must not contain domain-specific rules.
- Domain logic must not own orchestration lifecycle.

## 7. Vertical Slice Strategy

HMIP is developed by vertical slices. The first slice is PRC-001:

- Daily Beer Price Collection
- end-to-end flow: collect → extract → validate → compare → decide → alert / human_review

Vertical slice implementation must always include:
- workflow definition
- prompt
- schema
- skill/adapter
- decision logic
- tests
- lineage handling

## 8. Quality Bar

A capability is only considered complete when:
- it has a clear contract,
- it is mapped to repository paths,
- it has tests,
- it has observability where needed,
- it does not violate boundaries,
- it can be executed end-to-end or explicitly deferred with rationale.

## 9. Implementation Guidance for Claude

When Claude implements HMIP:
- keep core, domain, knowledge, platform, and tests boundaries strict,
- do not invent new architecture decisions without ADR,
- do not place implementation code in specification documents,
- use the system spec as the source of truth for architecture and scope.