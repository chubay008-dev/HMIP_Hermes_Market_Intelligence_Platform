# HMIP — Acceptance Criteria

## 1. Mục tiêu

Tài liệu này định nghĩa tiêu chí hoàn thành cho các sprint, module và vertical slice của HMIP. Mục tiêu là giúp Claude và team engineering biết rõ khi nào một thành phần được xem là xong, để tránh “gần xong” nhưng chưa đủ production-ready.

## 2. General acceptance principles

- Một feature chỉ được xem là hoàn thành nếu đạt DoD.
- Mọi contract trong spec phải được implement hoặc có lý do rõ ràng nếu deferred.
- Mọi module quan trọng phải có test tương ứng.
- Không merge nếu vi phạm architecture boundary.
- Không release nếu bootstrap, workflow, hoặc validation chưa ổn định.

## 3. Sprint acceptance criteria

### Sprint 1 — Foundation
- Repository skeleton đã tạo.
- ExecutionContext hoạt động.
- TaskRegistry có state machine.
- Bootstrap chạy thành công.
- Config loader skeleton hoạt động.
- Unit tests cho foundation pass.

### Sprint 2 — Runtime Core
- Event bus hoạt động.
- Planner/DAG executor xử lý workflow acyclic.
- Cycle detection pass.
- Workflow loading contract hoạt động.
- Integration tests cho core flow pass.

### Sprint 3 — PRC-001 Vertical Slice
- Workflow PRC-001 chạy end-to-end.
- Adapter thu thập dữ liệu hoạt động.
- Prompt extraction trả output đúng schema.
- Decision engine trả kết quả đúng policy.
- Lineage được ghi nhận.
- Workflow test pass.

### Sprint 4 — Knowledge & Lineage
- Ontology load/validate thành công.
- Brand/Product/SKU schema rõ ràng.
- Lineage records được tạo và lưu.
- Provenance trace có thể kiểm tra được.
- Tests cho knowledge và lineage pass.

### Sprint 5 — Testing & Quality
- Unit coverage đạt ngưỡng.
- Integration tests pass.
- Workflow regression tests pass.
- Prompt evaluation pass.
- Chaos tests cho failure modes chính pass.

### Sprint 6 — Deployment & Operations
- Docker image build thành công.
- Bootstrap chạy trong container.
- Health/readiness checks pass.
- Observability stack hoạt động.
- Deployment guide có thể làm theo được.

## 4. Module acceptance criteria

### Core runtime
- Registry state machine đúng contract.
- Config immutable sau bootstrap.
- ExecutionContext tạo unique id và trace id.
- Planner detect cycle đúng.
- Event bus publish/subscribe đúng.
- Error handling có taxonomy rõ.

### Domain workflow
- Workflow được parse thành DAG.
- Task dependencies đúng.
- Prompt output đúng schema.
- Decision engine đúng threshold.
- Escalation xảy ra khi confidence thấp.

### Knowledge
- Ontology versioned.
- Entities rõ quan hệ.
- Master/dynamic data tách biệt.
- Lineage có hash và trace context.

### Deployment
- Container chạy được ở môi trường mục tiêu.
- No secrets in image.
- Health/readiness behavior đúng.
- Startup command rõ và fail fast khi lỗi.

## 5. Definition of Done baseline

Mỗi module hoặc sprint phải đáp ứng tối thiểu:
- Code hoàn tất theo spec.
- Test pass.
- Lint/type check pass nếu áp dụng.
- Không vi phạm repository/file mapping.
- Có documentation cập nhật nếu contract thay đổi.
- Có rollback hoặc failure behavior nếu cần.

## 6. Quality gates

Không được coi là hoàn thành nếu:
- còn `TODO` cho contract cốt lõi,
- thiếu test cho đường lỗi,
- thiếu validation cho input chính,
- thiếu observability cho workflow quan trọng,
- thiếu lineage cho output quan trọng,
- còn ambiguity lớn giữa spec và code.

## 7. Claude implementation instruction

Khi Claude implement HMIP:
- chỉ đánh dấu hoàn thành khi đạt acceptance criteria tương ứng,
- không “đánh dấu xong” nếu chỉ chạy được một phần flow,
- ưu tiên pass acceptance trước khi mở sang sprint mới,
- nếu có phần deferred, phải ghi rõ lý do và trạng thái.