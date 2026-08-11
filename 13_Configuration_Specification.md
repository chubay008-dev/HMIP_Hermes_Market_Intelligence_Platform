# HMIP — Configuration Specification

## 1. Mục tiêu

Tài liệu này quy định chuẩn cấu hình cho HMIP, bao gồm cấu trúc file, thứ tự nạp, merge policy, validation rules, environment override, secret handling và immutable runtime config. Mục tiêu là giúp Claude sinh subsystem cấu hình nhất quán, an toàn và dễ kiểm thử.

## 2. Design principles

- Config phải rõ ràng, versioned và testable.
- Config sau bootstrap phải immutable.
- Không đọc env trực tiếp trong business logic nếu có thể tránh.
- Secret không được lưu plaintext trong file hoặc log.
- Cấu hình phải có ưu tiên nguồn rõ ràng.
- Merge policy phải deterministic.

## 3. Config sources

Các nguồn cấu hình hợp lệ:
- YAML files
- Environment variables
- CLI arguments
- Secret provider references
- Optional runtime overrides nếu policy cho phép

## 4. Config layers

Thứ tự ưu tiên đề xuất:
1. Base config
2. Environment config
3. Secret references
4. CLI overrides
5. Runtime overrides nếu được phép

## 5. Standard config files

### 5.1. `runtime.yaml`
Chứa:
- runtime version
- bootstrap settings
- registry behavior
- planner settings
- retry defaults
- concurrency settings

### 5.2. `workflow.yaml`
Chứa:
- workflow id
- version
- tasks
- retry policy
- compensation policy
- schema dependencies
- prompt dependencies
- skill dependencies

### 5.3. `knowledge.yaml`
Chứa:
- ontology version
- knowledge layer settings
- cache policy
- dynamic data refresh policy

### 5.4. `logging.yaml`
Chứa:
- log level
- structured logging settings
- output sink
- redaction policy

### 5.5. `deployment.yaml`
Chứa:
- environment name
- container settings
- health check behavior
- readiness behavior
- resource settings

## 6. Runtime config structure

### Example
```yaml
runtime:
  version: "1.6.1"
  bootstrap:
    strict_mode: true
    fail_fast: true
  planner:
    max_workers: 4
    detect_cycles: true
  registry: