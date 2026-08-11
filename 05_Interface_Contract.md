# HMIP — Interface Contract

## 1. Mục tiêu

Tài liệu này quy định các interface cốt lõi cho HMIP. Mục tiêu là chuẩn hóa cách các module, service, adapter, planner, event bus và workflow engine tương tác với nhau để Claude có thể sinh code nhất quán, ít suy đoán, và dễ kiểm thử.

## 2. Design principles

- Interface phải rõ ràng, nhỏ gọn và có trách nhiệm đơn nhất.
- Không để implementation leak vào contract.
- Ưu tiên explicit over implicit.
- Interface cốt lõi phải mock được trong test.
- Contract phải đủ chặt để suy ra input, output, side effects và error behavior.
- Không dùng interface quá trừu tượng nếu chưa có nhu cầu thực tế.

## 3. Contract rules

- Tất cả interface public phải có type hints.
- Interface phải mô tả rõ input, output và exception behavior.
- Không dùng `Any` trong contract trừ khi bất khả kháng; nếu có phải giới hạn ở boundary hẹp.
- Nếu một interface trả về result object, object đó phải có schema rõ ràng.
- Không để một interface gánh nhiều trách nhiệm không liên quan.
- Nếu interface bị trùng trách nhiệm với interface khác, phải tách hoặc đổi tên trước khi code.

## 4. Core interfaces

### 4.1. `BaseAdapter`

```python
class BaseAdapter(Protocol):
    def fetch(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def health(self) -> bool: ...
```

#### Rules
- `fetch()` lấy dữ liệu từ external system hoặc source bên ngoài.
- `health()` báo trạng thái sẵn sàng của adapter.
- Adapter không được chứa business decision logic.
- Nếu adapter cần validation nội bộ, validation đó chỉ áp dụng cho payload đầu vào/đầu ra của adapter.

### 4.2. `BaseSkill`

```python
class BaseSkill(Protocol):
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]: ...
    def rollback(self, context: dict[str, Any]) -> None: ...
```

#### Rules
- `run()` thực thi tác vụ domain cụ thể.
- `rollback()` chỉ dùng khi skill hỗ trợ compensation.
- Skill không được điều phối workflow.
- Skill không được gọi orchestration layer trực tiếp.

### 4.3. `WorkflowEngine`

```python
class WorkflowEngine(Protocol):
    def load(self, workflow_id: str) -> dict[str, Any]: ...
    def execute(self, workflow: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...
    def cancel(self, execution_id: str) -> None: ...
```

#### Rules
- `load()` đọc workflow definition đã versioned.
- `execute()` chạy workflow trong execution context.
- `cancel()` hủy execution nếu policy cho phép.
- `WorkflowEngine` không nên gánh trách nhiệm planning chi tiết nếu `Planner` đã tồn tại.

### 4.4. `Planner`

```python
class Planner(Protocol):
    def plan(self, workflow: dict[str, Any]) -> dict[str, Any]: ...
    def detect_cycles(self, workflow: dict[str, Any]) -> bool: ...
```

#### Rules
- `plan()` chuyển workflow thành execution plan hoặc DAG plan.
- `detect_cycles()` phải fail fast nếu có circular dependency.
- Planner không được gọi external side effects.
- Planner chỉ chịu trách nhiệm tạo và kiểm tra plan, không thực thi task.

### 4.5. `EventBus`

```python
class EventBus(Protocol):
    def publish(self, event: dict[str, Any]) -> None: ...
    def subscribe(self, event_type: str, handler: Callable[[dict[str, Any]], None]) -> None: ...
    def unsubscribe(self, event_type: str, handler: Callable[[dict[str, Any]], None]) -> None: ...
```

#### Rules
- `publish()` phát event nội bộ hoặc event orchestration.
- `subscribe()` đăng ký handler cho một event type cụ thể.
- `unsubscribe()` bỏ đăng ký handler.
- Event bus không được chứa business logic.
- Handler signature phải rõ và ổn định.

### 4.6. `Registry`

```python
class Registry(Protocol):
    def register(self, task: dict[str, Any]) -> None: ...
    def freeze(self) -> None: ...
    def get_task(self, name: str) -> dict[str, Any] | None: ...
    def list_tasks(self) -> list[dict[str, Any]]: ...
    @property
    def state(self) -> str: ...
    def transition_to(self, state: str) -> None: ...
```

#### Rules
- `register()` chỉ hợp lệ khi registry ở state cho phép.
- `freeze()` khóa registry sau bootstrap.
- `get_task()` trả về `None` nếu không tồn tại.
- `list_tasks()` trả về snapshot an toàn.
- `state` phải phản ánh lifecycle thực tế.
- `transition_to()` chỉ cho phép các state hợp lệ theo state machine đã chốt.

### 4.7. `ConfigLoader`

```python
class ConfigLoader(Protocol):
    def load(self) -> dict[str, Any]: ...
    def merge(self, *configs: dict[str, Any]) -> dict[str, Any]: ...
    def validate(self, config: dict[str, Any]) -> None: ...
    def freeze(self, config: dict[str, Any]) -> object: ...
```

#### Rules
- `load()` đọc từ YAML, env, CLI hoặc source được chấp nhận.
- `merge()` phải deep merge deterministic.
- `validate()` phải fail nếu config không hợp lệ.
- `freeze()` phải trả về config immutable hoặc object bất biến tương đương.
- ConfigLoader không được tự ý resolve secret ngoài rule đã chốt.

### 4.8. `LineageTracer`

```python
class LineageTracer(Protocol):
    def record_trace(
        self,
        step_id: str,
        input_val: Any,
        output_val: Any,
        model_info: str,
    ) -> None: ...
```

#### Rules
- Trace phải đủ để audit và reproducibility.
- Không ghi secret plaintext.
- `record_trace()` phải append-only về mặt semantics.

### 4.9. `DecisionEngine`

```python
class DecisionEngine(Protocol):
    def evaluate(self, current_price: float, base_price: float) -> str: ...
```

#### Rules
- Chỉ trả output thuộc tập quyết định cho phép.
- Phải xử lý trường hợp `base_price <= 0`.
- Phải có threshold rõ ràng.
- Không thay đổi input data.

## 5. Data contract interfaces

### 5.1. `ExecutionContext`

```python
@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str
    trace_id: str
    correlation_id: str
    epoch: int
    timestamp: float
    metadata: dict[str, Any]
```

### 5.2. `TaskExecutionResult`

```python
@dataclass(frozen=True)
class TaskExecutionResult:
    task_name: str
    status: str
    duration_ms: float
    error: str | None = None
```

### 5.3. `BootstrapReport`

```python
@dataclass(frozen=True)
class BootstrapReport:
    execution_id: str
    status: str
    task_results: tuple[TaskExecutionResult, ...]
    runtime_version: str = "1.6.1"
    kernel_version: str = "RC2.1"
```

### 5.4. `DecisionResult`

```python
@dataclass(frozen=True)
class DecisionResult:
    decision: str
    confidence: float
    reason: str
    recommended_action: str | None = None
```

## 6. Exception behavior

Mỗi interface phải xác định rõ:
- khi nào raise exception,
- khi nào return `None`,
- khi nào return empty collection,
- exception đó có retryable hay không.

### General rules
- Registry errors phải raise `RegistryStateException`.
- Config errors phải raise `ConfigValidationException`.
- Workflow parsing errors phải raise `WorkflowParseException`.
- Workflow runtime failures phải raise `WorkflowExecutionException`.
- Decision errors phải raise `DecisionEngineException`.

## 7. Async boundary rules

- Chỉ dùng async nếu interface đó rõ ràng yêu cầu I/O concurrency.
- Không ép tất cả interface sang async nếu không cần.
- Nếu một interface là async, toàn bộ call chain liên quan phải nhất quán.
- Không mix sync/async tùy tiện trong cùng contract.

## 8. Mockability rules

- Mọi interface cốt lõi phải mock được trong unit test.
- Không phụ thuộc trực tiếp vào concrete implementation trong domain logic.
- Test double phải dễ tạo mà không cần boot toàn hệ thống.

## 9. Claude implementation instruction

Khi Claude implement HMIP:
- ưu tiên interface trước implementation,
- không thêm method ngoài contract nếu chưa được chốt,
- nếu cần thay đổi interface, hãy cập nhật tài liệu trước,
- luôn tạo test dựa trên contract,
- dùng interface để tách core khỏi domain và external integration.