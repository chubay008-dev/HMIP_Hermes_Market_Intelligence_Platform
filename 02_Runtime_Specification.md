# HMIP — Runtime Specification

## 1. Mục tiêu

Tài liệu này quy định runtime core của HMIP, bao gồm bootstrap, execution context, registry, planner, event bus, config subsystem, validator, observability, lineage và feedback loop. Mục tiêu là giúp Claude sinh core runtime theo đúng boundary, đúng lifecycle và đúng contract.

## 2. Runtime principles

- Runtime phải deterministic ở mức contract.
- Bootstrap phải fail fast nếu core dependency thiếu.
- Registry phải có lifecycle state machine rõ ràng.
- Config phải immutable sau bootstrap.
- Workflow phải được plan thành DAG trước khi execution.
- Mọi output quan trọng phải có trace và lineage.
- Runtime không được chứa business logic ngành cụ thể.

## 3. Runtime layers

### 3.1. Bootstrap layer
Chịu trách nhiệm:
- load environment,
- load config,
- initialize logging,
- initialize container,
- initialize registry,
- register tasks/plugins,
- freeze registry,
- validate runtime,
- emit bootstrap report.

### 3.2. Control layer
Chịu trách nhiệm:
- orchestrate lifecycle,
- manage state transitions,
- enforce policy,
- dispatch events,
- coordinate workflow execution.

### 3.3. Execution layer
Chịu trách nhiệm:
- execute workflow plan,
- call adapters/skills,
- perform validation,
- collect results,
- emit lineage and decision outputs.

### 3.4. Observability layer
Chịu trách nhiệm:
- structured logging,
- metrics,
- tracing,
- lineage capture,
- audit support.

## 4. Core modules

- `context`
- `container`
- `registry`
- `planner`
- `event_bus`
- `config`
- `validator`
- `observability`
- `lineage`
- `feedback_loop`
- `orchestrator`

## 5. ExecutionContext

### Purpose
ExecutionContext là đối tượng xuyên suốt một lần execution, dùng để liên kết mọi hành vi runtime, workflow, trace và lineage.

### Required fields
- `execution_id: str`
- `trace_id: str`
- `correlation_id: str`
- `epoch: int`
- `timestamp: float`
- `metadata: dict[str, Any]`

### Optional fields
- `tenant_id: str | None`
- `actor_id: str | None`
- `request_id: str | None`
- `parent_trace_id: str | None`
- `policy_version: str | None`

### Rules
- `execution_id` phải unique.
- `trace_id` phải duy nhất cho distributed trace hoặc execution trace.
- `correlation_id` gom các bước thuộc cùng business transaction.
- `metadata` phải structured và immutable nếu có thể.

## 6. TaskRegistry

### Purpose
Registry quản lý task, skill, plugin hoặc execution artifact đã được đăng ký trước khi runtime chạy business workflow.

### Responsibilities
- register task,
- freeze registry,
- read task by name,
- list tasks,
- enforce lifecycle states,
- prevent duplicate registration.

### Lifecycle states
- `READY`
- `FROZEN`
- `EXECUTING`
- `COMPLETED`
- `FAILED`

### Rules
- chỉ register khi `READY`.
- sau `freeze()` không cho register mới.
- transition phải hợp lệ theo state machine.
- mọi mutation phải thread-safe nếu runtime chạy đa luồng.

## 7. BootstrapKernel

### Purpose
BootstrapKernel là điểm khởi động đầu tiên của runtime.

### Bootstrap order
1. Load environment.
2. Resolve base config.
3. Initialize logging.
4. Initialize container.
5. Initialize registry.
6. Register tasks and plugins.
7. Freeze registry.
8. Build runtime context.
9. Validate runtime.
10. Emit bootstrap report.

### Rules
- bootstrap fail fast nếu dependency core thiếu.
- bootstrap report phải chứa trạng thái và kết quả từng bước.
- bootstrap phải là bước duy nhất có quyền chuẩn bị runtime trước execution.

## 8. Configuration subsystem

### Purpose
Subsytem cấu hình nạp, hợp nhất, xác thực và freeze cấu hình runtime.

### Pipeline
1. Load.
2. Deep merge.
3. Expand variables.
4. Resolve secrets.
5. Validate schema.
6. Validate runtime.
7. Generate fingerprint.
8. Create sanitized snapshot.
9. Bind manifest metadata.
10. Record provenance.
11. Tag identity.
12. Freeze final config object.

### Policies
- `SAFE_DYNAMIC`
- `RESTART_REQUIRED`
- `CLUSTER_RESTART`
- `IMMUTABLE`

### Rules
- merge phải deterministic.
- config sau bootstrap phải immutable.
- secret phải resolve qua abstraction.
- fingerprint phải dùng canonical normalized config.

## 9. EventBus

### Purpose
EventBus cung cấp cơ chế publish/subscribe giữa các runtime components.

### Responsibilities
- publish event,
- subscribe handler,
- unsubscribe handler,
- dispatch event theo type.

### Rules
- event bus không được chứa business logic.
- handler signature phải ổn định và testable.
- event phải có trace context nếu dùng cho runtime coordination.

## 10. Planner / DAG executor

### Purpose
Planner chuyển workflow definition thành execution plan hoặc DAG.

### Responsibilities
- plan workflow,
- detect cycle,
- topologically order tasks,
- prepare execution graph.

### Rules
- fail fast nếu có cycle.
- không gọi external side effects.
- không thực thi business logic.
- kết quả plan phải dùng được bởi workflow engine.

## 11. Validator

### Purpose
Validator kiểm tra schema, payload, runtime invariants và boundary constraints.

### Rules
- dữ liệu không hợp lệ phải fail fast hoặc route vào escalation.
- validator phải test được.
- schema validation phải tách biệt khỏi decision logic.

## 12. Lineage

### Purpose
Lineage ghi lại chuỗi biến đổi dữ liệu, output, decision và resolution trace.

### Rules
- append-only về mặt semantics.
- không ghi secret plaintext.
- mỗi trace phải có step_id, input, output, model_info, timestamp và hash.
- trace phải đủ để audit và reproducibility.

## 13. Feedback loop

### Purpose
Feedback loop hỗ trợ human-in-the-loop và escalation.

### Rules
- chỉ kích hoạt khi policy yêu cầu hoặc confidence thấp.
- không tự ý thay decision engine.
- phải có trace/audit record.

## 14. Observability

### Requirements
- structured JSON logging,
- metrics theo workflow/task/bootstrap,
- tracing xuyên suốt execution,
- correlation giữa logs, metrics và lineage.

### Minimum log fields
- timestamp
- execution_id
- trace_id
- component
- event_type
- status
- duration_ms
- error_code

## 15. Error handling

### Core error categories
- bootstrap failure
- config failure
- dependency failure
- validation failure
- permission failure
- runtime execution failure

### Rules
- error phải có code rõ.
- error phải đủ ngữ cảnh.
- lỗi retryable phải được đánh dấu nếu cần.
- core runtime không được nuốt lỗi im lặng.

## 16. Claude implementation instruction

Khi Claude implement runtime:
- giữ mọi runtime behavior deterministic theo contract,
- không thêm business logic vào runtime core,
- không thay đổi state machine nếu chưa có ADR/spec mới,
- luôn tạo test cho registry, bootstrap, config, planner, event bus và lineage,
- đảm bảo runtime core tách biệt khỏi domain logic.