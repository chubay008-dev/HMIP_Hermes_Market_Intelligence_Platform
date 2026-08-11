# HMIP — Domain Specification

## 1. Mục tiêu

Tài liệu này quy định cách tổ chức domain layer của HMIP theo mô hình DDD và vertical slice. Mục tiêu là bảo đảm business logic được cô lập rõ ràng khỏi core runtime, đồng thời cho phép Claude sinh domain code đúng boundary, đúng workflow và đúng contract.

## 2. Domain principles

- Domain layer chỉ chứa business logic thực sự.
- Domain phải được chia theo vertical slice.
- Mỗi domain pack phải có boundary rõ ràng.
- Workflow, skill, prompt, schema và decision logic của domain phải đặt gần nhau.
- Core runtime không chứa rule nghiệp vụ đặc thù ngành.
- Domain không điều phối bootstrap hoặc runtime lifecycle.

## 3. Domain packs

Ví dụ các domain pack:
- `beer/pricing`
- `retail/promo`
- `pharma/intelligence`
- `competitor/watch`

Mỗi domain pack nên có:
- workflows
- prompts
- schemas
- skills/adapters
- decision rules
- tests
- docs

## 4. Domain workflow contract

Mỗi workflow phải define:
- `id`
- `version`
- `owner`
- `status`
- `risk`
- `tasks`
- `inputs`
- `outputs`
- `retry_policy`
- `compensation_policy`
- `schema_dependencies`
- `prompt_dependencies`
- `skill_dependencies`

### Rules
- Workflow phải versioned.
- Workflow phải parse được thành DAG.
- Workflow không được chứa decision logic phức tạp nếu decision engine đã chịu trách nhiệm.
- Workflow không được phụ thuộc vào file chưa khai báo trong contract.
- Workflow không được tự ý mở rộng scope ngoài domain pack của nó.

## 5. Task contract

Mỗi task phải define:
- `id`
- `type`
- `input`
- `output`
- `dependencies`
- `retry_policy`
- `timeout`
- `failure_modes`

### Task types
- `adapter`
- `prompt`
- `schema_validate`
- `decision`
- `notify`
- `transform`
- `persist`

## 6. PRC-001 vertical slice

### Business goal
Daily beer price collection from external sources, followed by extraction, validation, comparison, decision, and escalation if needed.

### High-level flow
1. `collect`
2. `extract`
3. `validate`
4. `compare`
5. `decide`
6. `alert` / `human_review`

### Required artifacts
- `domains/beer/pricing/workflows/WF-PRC-001.yaml`
- `domains/beer/pricing/prompts/extract_price.md`
- `domains/beer/pricing/schemas/schema.json`
- `domains/beer/pricing/skills/collect_price.py`
- `domains/beer/pricing/decision_engine.py`
- related tests

### Required runtime behavior
- collect raw price payload,
- extract structured data,
- validate output schema,
- compare against reference/base price,
- apply decision policy,
- record lineage,
- escalate when confidence is low or variance policy is violated.

## 7. Decision engine

Decision engine is responsible for evaluating normalized outputs and returning a high-level decision.

### Allowed outputs
- `IGNORE`
- `ALERT`
- `ESCALATE`
- `HUMAN_REVIEW`

### Rules
- Decision engine must not mutate raw data.
- Thresholds must be explicit.
- Confidence below threshold must route to human review or escalation.
- Decision trace must be recorded.
- Decision engine must be testable in isolation.

## 8. Adapter rules

- Adapter only handles external integration.
- Adapter must not contain business decision logic.
- Adapter should return raw or semi-structured data.
- Adapter must handle timeout, retry, and failure modes.
- Adapter should be mockable and replaceable.

## 9. Prompt rules

- Prompt output must be structured, preferably JSON.
- Prompt must be versioned.
- Prompt must define output contract clearly.
- Prompt must not generate unnecessary narrative.
- Prompt files are domain artifacts, not core runtime artifacts.

## 10. Schema rules

- Domain schema must match data contract.
- Schema must be versioned if used in production flow.
- Schema validation must be deterministic.
- Schema changes must update tests and workflow dependencies.

## 11. Escalation rules

Escalation is required when:
- confidence is low,
- input is incomplete or unreliable,
- policy requires human approval,
- repeated task failures occur,
- business risk is high.

## 12. Domain boundaries

- Domain code must not control bootstrap.
- Domain code must not manage registry lifecycle.
- Domain code must not own runtime config freeze.
- Domain code must not bypass validators or policy enforcement.
- Domain code must stay within the domain pack boundary.

## 13. Claude implementation instruction

When Claude implements domain code:
- keep domain code near the relevant workflow,
- do not move orchestration into domain logic,
- do not place domain rules in core,
- create tests for domain behaviors,
- keep workflow and decision responsibilities separated,
- update traceability matrix if a new capability is added.