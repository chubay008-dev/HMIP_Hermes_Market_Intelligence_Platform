# HMIP — Glossary

## AI Operating System (AI OS)
Mô hình hệ thống trong đó AI không chỉ là một tính năng, mà là lớp runtime trung tâm điều phối workflow, dữ liệu, công cụ và decisioning.

## ADR
Architecture Decision Record. Tài liệu ghi lại quyết định kiến trúc, bối cảnh, lý do, hệ quả và trade-off.

## Adapter
Lớp tích hợp với hệ thống bên ngoài như API, website, scraper, storage hoặc secrets provider.

## Bootstrap
Quá trình khởi động hệ thống, bao gồm load config, init registry, register plugins/tasks, validate runtime và freeze state.

## Boundary
Ranh giới trách nhiệm giữa các layer hoặc module. Ví dụ: core không chứa business logic.

## Capability
Một năng lực nghiệp vụ có thể triển khai thành vertical slice, workflow, skill, prompt và schema.

## Configuration Subsystem
Hệ thống nạp, merge, validate, fingerprint và freeze cấu hình runtime.

## Correlation ID
Mã dùng để gom các bước thuộc cùng một business transaction hoặc execution chain.

## DAG (Directed Acyclic Graph)
Đồ thị có hướng không chu trình, dùng để biểu diễn dependency và lập lịch task.

## Decision Engine
Thành phần đánh giá dữ liệu đã chuẩn hóa để đưa ra quyết định ở mức cao như `IGNORE`, `ALERT`, `ESCALATE`, `HUMAN_REVIEW`.

## Domain Pack
Gói domain chứa workflow, skill, prompt, schema, test và docs cho một lát cắt nghiệp vụ.

## Epoch
Phiên bản trạng thái bootstrap hoặc config generation tại một thời điểm xác định.

## Event Bus
Lớp phát và nhận event giữa các thành phần runtime, orchestrator và workflow engine.

## Execution Context
Đối tượng đại diện cho một lần chạy hệ thống, chứa execution_id, trace_id, correlation_id và metadata.

## Fingerprint
Mã hash dùng để xác định trạng thái cấu hình hoặc dữ liệu canonical, phục vụ drift detection.

## Freeze
Trạng thái khóa bất biến sau bootstrap hoặc sau khi registry/config đã hoàn tất nạp.

## Hermes Agent
Orchestrator trung tâm duy nhất của HMIP, chịu trách nhiệm điều phối workflow và xử lý vòng đời execution.

## Human Review
Cơ chế chuyển kết quả sang người dùng hoặc operator khi confidence thấp hoặc policy yêu cầu xác nhận.

## Immutable Config
Cấu hình không cho phép mutation sau bootstrap nếu không có policy reload riêng.

## Knowledge Layer
Lớp lưu ontology, master data, dynamic intelligence và lineage-related artifacts.

## Lineage
Dấu vết nguồn gốc và chuỗi biến đổi của dữ liệu, quyết định hoặc output.

## Master Data
Dữ liệu gốc, ổn định, dùng làm nguồn chuẩn cho domain và knowledge layer.

## Orchestrator
Thành phần điều phối execution, workflow và lifecycle. Trong HMIP, orchestrator duy nhất là Hermes.

## Ontology
Mô hình khái niệm và quan hệ giữa các thực thể như Brand, Product, SKU.

## Provenance
Thông tin về nguồn gốc, lịch sử và đường đi của dữ liệu hoặc output.

## Registry
Kho đăng ký task, plugin hoặc skill, có state machine và được freeze sau bootstrap.

## Retry Policy
Chính sách thử lại khi task hoặc adapter thất bại do lỗi tạm thời.

## Runtime
Lớp vận hành hệ thống, bao gồm bootstrap, registry, config, planner, event bus, validation và observability.

## Single-Agent Autonomous
Mô hình HMIP dùng một orchestrator trung tâm duy nhất thay vì nhiều agent điều phối cạnh tranh.

## Skill
Đơn vị thực thi tác vụ kỹ thuật hoặc nghiệp vụ cụ thể, thường nằm trong domain pack.

## Snapshot
Bản sao đã sanitize và lưu trạng thái cấu hình hoặc dữ liệu tại một thời điểm.

## State Machine
Mô hình chuyển trạng thái hữu hạn cho registry, bootstrap, workflow hoặc config lifecycle.

## Trace ID
Mã định danh cho distributed trace hoặc execution trace xuyên suốt hệ thống.

## Vertical Slice
Phương pháp phát triển một năng lực nghiệp vụ end-to-end, từ hạ tầng đến workflow, decisioning và testing.