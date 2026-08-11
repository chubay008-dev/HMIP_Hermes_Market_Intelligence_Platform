# HMIP — ADR Details

## 1. Mục tiêu

Tài liệu này mở rộng các quyết định kiến trúc (ADR) cốt lõi của HMIP với bối cảnh, lý do, trade-off và hệ quả. Mục tiêu là giảm mơ hồ khi Claude hoặc team engineering triển khai hệ thống, đặc biệt ở các điểm có thể đi theo nhiều hướng kỹ thuật khác nhau.

## 2. ADR format

Mỗi ADR nên gồm:
- ID
- Title
- Status
- Context
- Decision
- Rationale
- Consequences
- Trade-offs
- Notes

## 3. ADR-001 — Single-Agent Autonomous

### Status
Accepted

### Context
HMIP phải xử lý nhiều workflow và domain, nhưng muốn giữ nhất quán trạng thái và giảm xung đột orchestration.

### Decision
Chỉ sử dụng một orchestrator trung tâm: Hermes Agent.

### Rationale
- Giảm conflict giữa nhiều agent.
- Dễ audit và trace.
- Dễ kiểm soát policy và lifecycle.

### Consequences
- Tăng tính nhất quán.
- Có single point of failure nếu Hermes lỗi.

### Trade-offs
- Giảm song song ở mức agent orchestration.
- Cần bootstrap và observability mạnh hơn.

## 4. ADR-002 — Vertical Slice First

### Status
Accepted

### Context
Big upfront design dễ dẫn đến phân tích quá mức và chậm ra giá trị.

### Decision
Phát triển theo vertical slice end-to-end.

### Rationale
- Tạo giá trị sớm.
- Kiến trúc được chứng minh bằng runtime.
- Dễ điều chỉnh dựa trên feedback.

### Consequences
- Cần discipline tốt về boundary.
- Mỗi slice phải độc lập và testable.

### Trade-offs
- Chậm hơn ở tầm kiến trúc tổng thể nếu nhìn ngắn hạn.
- Nhưng an toàn hơn về mặt thực thi.

## 5. ADR-003 — DAG-Based Workflow Execution

### Status
Accepted

### Context
Workflow có dependency phức tạp, cần deterministic order.

### Decision
Dùng DAG executor với topological ordering.

### Rationale
- Tránh circular dependency.
- Rõ dependency chain.
- Hỗ trợ retry và compensation theo node.

### Consequences
- Workflow definition phải chặt.
- Cần cycle detection trước execution.

### Trade-offs
- Ít linh hoạt hơn sequential ad-hoc execution.
- Nhưng ổn định và audit tốt hơn.

## 6. ADR-004 — YAML for Workflow Definitions

### Status
Accepted

### Context
Workflow cần dễ đọc, dễ review và version control tốt.

### Decision
Dùng YAML cho workflow definitions.

### Rationale
- Human-readable.
- Phù hợp cho config-like artifact.
- Dễ versioning.

### Consequences
- Cần schema validation nghiêm ngặt.
- Phải xử lý cú pháp và indentation cẩn thận.

### Trade-offs
- JSON chặt hơn.
- YAML thân thiện hơn cho người đọc.

## 7. ADR-005 — Separation of Workflow and Decision Engine

### Status
Accepted

### Context
Orchestration và decisioning là hai responsibility khác nhau.

### Decision
Workflow chỉ điều phối; decision engine chỉ đánh giá và đề xuất quyết định.

### Rationale
- Dễ test.
- Dễ thay policy.
- Tránh trộn logic.

### Consequences
- Cần contract rõ giữa hai lớp.
- Tăng số lượng artifact cần quản lý.

### Trade-offs
- Nhiều thành phần hơn.
- Nhưng cấu trúc sạch hơn.

## 8. ADR-006 — Adapter Pattern for External Integration

### Status
Accepted

### Context
HMIP phải tích hợp external system, website, API, scraper, storage, secrets provider.

### Decision
Mọi integration phải đi qua adapter layer.

### Rationale
- Tách core khỏi thay đổi external.
- Dễ mock.
- Dễ thay provider.

### Consequences
- Cần interface ổn định.
- Adapter phải có timeout/retry/failure rules.

### Trade-offs
- Thêm một lớp trừu tượng.
- Nhưng giảm coupling đáng kể.

## 9. ADR-007 — Immutable Config After Bootstrap

### Status
Accepted

### Context
Config mutate tùy tiện sau bootstrap gây drift và khó audit.

### Decision
Config sau bootstrap phải immutable.

### Rationale
- Dễ tái tạo runtime state.
- Giảm drift.
- Tăng tính an toàn.

### Consequences
- Cần reload policy riêng nếu muốn thay đổi runtime.
- Secret rotation phải thiết kế kỹ.

### Trade-offs
- Ít linh hoạt hơn.
- Nhưng đáng tin cậy hơn.

## 10. ADR-008 — Structured Logging and Tracing

### Status
Accepted

### Context
Enterprise runtime cần observability và audit tốt.

### Decision
Dùng structured JSON logging và tracing xuyên suốt.

### Rationale
- Dễ query.
- Dễ debug.
- Dễ liên kết event → workflow → task.

### Consequences
- Cần chuẩn hóa field names.
- Có thêm overhead nhẹ.

### Trade-offs
- Logging phức tạp hơn plain text.
- Nhưng giá trị vận hành cao hơn.

## 11. ADR-009 — Python 3.12 + Strict Typing

### Status
Accepted

### Context
HMIP cần code hiện đại, maintainable và rõ contract.

### Decision
Dùng Python 3.12, ruff, strict mypy, pytest, uv.

### Rationale
- Tăng chất lượng code.
- Phát hiện lỗi sớm.
- Chuẩn hóa style.

### Consequences
- Yêu cầu discipline cao hơn.
- Ít linh hoạt với code quá động.

### Trade-offs
- Học và tuân thủ nghiêm ngặt hơn.
- Nhưng độ ổn định tốt hơn.

## 12. ADR-010 — Playwright for Browser-Based Scraping

### Status
Proposed / Accepted if needed

### Context
Một số nguồn dữ liệu web cần browser automation.

### Decision
Dùng Playwright cho scraping production khi nguồn cần browser behavior.

### Rationale
- Tương thích web động tốt.
- Dễ xử lý SPA / rendered pages.

### Consequences
- Container phức tạp hơn.
- Cần system dependencies.

### Trade-offs
- Nặng hơn HTTP scraping.
- Nhưng đáng tin cậy hơn trong nhiều case thực tế.

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