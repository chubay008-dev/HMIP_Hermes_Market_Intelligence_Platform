# HMIP — Architecture Decision Records (ADR)

## 1. Mục tiêu

Tài liệu này ghi lại các quyết định kiến trúc cốt lõi của HMIP và lý do đằng sau các quyết định đó. Mục tiêu là giảm mơ hồ khi Claude hoặc con người triển khai hệ thống, tránh việc tự ý thay đổi nguyên tắc thiết kế trong quá trình code.

## 2. ADR format

Mỗi ADR nên có:
- ID
- Title
- Status
- Context
- Decision
- Consequences

## 3. ADR-001 — Single-Agent Autonomous

### Status
Accepted

### Context
Hệ thống HMIP có nhiều workflow và domain khác nhau. Việc cho nhiều agent cùng điều phối dễ gây xung đột trạng thái, trùng quyền điều khiển, và khó audit.

### Decision
Chỉ sử dụng một orchestrator trung tâm: Hermes Agent.

### Consequences
- State consistency cao hơn.
- Giảm orchestration conflicts.
- Dễ audit và debug hơn.
- Có single point of failure nếu Hermes lỗi, nên cần bootstrap, recovery và observability tốt.

## 4. ADR-002 — Use Vertical Slice Architecture

### Status
Accepted

### Context
Big upfront design thường dẫn đến phân tích quá mức và chậm tạo giá trị thực tế.

### Decision
Phát triển theo vertical slice, ưu tiên end-to-end implementation cho từng capability cụ thể.

### Consequences
- Tạo value sớm.
- Kiến trúc được chứng minh bằng runtime.
- Dễ triển khai incrementally.
- Cần kỷ luật tốt để không làm rối domain boundaries.

## 5. ADR-003 — Use DAG-based Workflow Execution

### Status
Accepted

### Context
Workflow của HMIP có nhiều task phụ thuộc lẫn nhau, cần chạy theo đúng thứ tự và tránh circular dependency.

### Decision
Dùng DAG executor với topological ordering.

### Consequences
- Dependency resolution rõ ràng.
- Cycle detection có thể thực thi trước.
- Hỗ trợ retry và compensation theo node.
- Yêu cầu workflow definition phải chặt chẽ.

## 6. ADR-004 — Use YAML for Workflow Definitions

### Status
Accepted

### Context
Workflow cần readable, dễ viết, dễ review, và phù hợp cho cấu hình được versioned.

### Decision
Dùng YAML cho workflow definitions.

### Consequences
- Dễ đọc hơn JSON trong nhiều case.
- Có thể version control tốt.
- Cần validation nghiêm ngặt để tránh sai cú pháp.
- Phải có schema validation.

## 7. ADR-005 — Separate Workflow and Decision Engine

### Status
Accepted

### Context
Workflow orchestration và decision making là hai responsibility khác nhau.

### Decision
Workflow chỉ chịu trách nhiệm điều phối và dữ liệu; decision engine chỉ chịu trách nhiệm đánh giá và đưa ra quyết định mức cao.

### Consequences
- Code rõ hơn.
- Dễ test hơn.
- Dễ thay decision policy mà không sửa workflow orchestration.
- Cần contract rõ giữa hai lớp.

## 8. ADR-006 — Use Adapter Pattern for External Integration

### Status
Accepted

### Context
HMIP sẽ kết nối với website, API, scraper, storage, secrets provider, và các hệ thống ngoài.

### Decision
Mọi external integration phải đi qua adapter layer.

### Consequences
- Tách core khỏi thay đổi từ bên ngoài.
- Dễ mock trong test.
- Dễ thay đổi provider.
- Cần thiết kế interface ổn định.

## 9. ADR-007 — Use Immutable Config After Bootstrap

### Status
Accepted

### Context
Config thay đổi tùy tiện trong runtime dễ gây drift và khó audit.

### Decision
Config sau bootstrap phải immutable.

### Consequences
- Tăng tính nhất quán.
- Dễ tái tạo runtime state.
- Cần cơ chế reload riêng nếu có dynamic config.
- Secret rotation phải được thiết kế cẩn thận.

## 10. ADR-008 — Use Structured Logging and Tracing

### Status
Accepted

### Context
Enterprise runtime cần audit, observability, và root cause analysis.

### Decision
Dùng structured JSON logging và tracing xuyên suốt workflow.

### Consequences
- Dễ query và phân tích.
- Hỗ trợ troubleshooting tốt hơn.
- Cần standard hóa field names.
- Có thể tăng chút overhead runtime.

## 11. ADR-009 — Prefer Python 3.12 + Strict Typing

### Status
Accepted

### Context
HMIP cần code hiện đại, maintainable, và rõ contract.

### Decision
Dùng Python 3.12, ruff, strict mypy, pytest, uv.

### Consequences
- Code thống nhất hơn.
- Dễ phát hiện lỗi sớm.
- Cần discipline cao hơn khi viết code.
- Giảm độ linh hoạt với code rất động.

## 12. ADR-010 — Use Playwright for Browser-Based Scraping

### Status
Proposed / Accepted if needed

### Context
Một số nguồn dữ liệu web cần browser automation.

### Decision
Dùng Playwright cho scraping production khi nguồn cần browser behavior.

### Consequences
- Tương thích web động tốt.
- Dễ xử lý SPA / rendered pages.
- Container phức tạp hơn.
- Cần system dependencies.

## 13. Change policy

- Không sửa ADR đã accepted nếu chưa có lý do mạnh.
- Nếu quyết định mới mâu thuẫn với ADR cũ, phải tạo ADR mới hoặc cập nhật status rõ ràng.
- Claude không được tự ý thay đổi ADR.

## 14. Claude implementation instruction

Khi Claude triển khai HMIP:
- tuân thủ ADR hiện có,
- không tự ý thay architecture decision,
- nếu thiếu ADR, hãy đề xuất thay vì đoán,
- ưu tiên giải pháp phù hợp với quyết định đã accepted.