# HMIP — Testing Standard

## 1. Mục tiêu

Tài liệu này quy định chuẩn kiểm thử cho HMIP. Mục tiêu là đảm bảo mọi thành phần của hệ thống được kiểm chứng theo đúng responsibility, contract, và architecture boundary trước khi merge hoặc release.

## 2. Testing principles

- Mọi public behavior phải có test.
- Mọi bug fix phải đi kèm regression test.
- Test phải deterministic, dễ đọc, dễ chạy lại.
- Test không được phụ thuộc vào state ngẫu nhiên nếu không kiểm soát được.
- Boundary giữa core, domain, knowledge và platform phải được test riêng.
- Không viết test quá phụ thuộc vào implementation detail nếu có thể test contract.

## 3. Testing layers

### 3.1. Unit test
Mục tiêu:
- kiểm tra logic nhỏ nhất,
- mock các dependency ngoài,
- chạy nhanh,
- xác định rõ input/output.

Phạm vi:
- registry,
- config loader,
- context factory,
- decision engine,
- validator,
- utility functions.

### 3.2. Integration test
Mục tiêu:
- kiểm tra tương tác giữa các module,
- test boundary thật sự quan trọng,
- sử dụng fake hoặc sandbox dependency khi cần.

Phạm vi:
- orchestrator + registry,
- planner + workflow definition,
- workflow + adapter,
- config + secret resolver,
- lineage + execution flow.

### 3.3. Workflow test
Mục tiêu:
- kiểm tra end-to-end cho một vertical slice,
- xác nhận workflow chạy đúng contract,
- xác nhận output đúng schema và policy.

Phạm vi:
- PRC-001 Daily Beer Price Collection,
- các workflow business quan trọng khác.

### 3.4. Prompt evaluation test
Mục tiêu:
- kiểm tra chất lượng output của prompt,
- đánh giá trên golden dataset hoặc expected output set,
- đảm bảo output contract ổn định.

Phạm vi:
- extraction prompt,
- decision prompt nếu có,
- classification prompt nếu có.

### 3.5. Chaos / fault injection test
Mục tiêu:
- kiểm tra khả năng chịu lỗi,
- kiểm tra rollback/compensation,
- mô phỏng sự cố thật.

Phạm vi:
- storage failure,
- network timeout,
- disk full,
- deadlock,
- dependency unavailable.

## 4. Coverage policy

### Minimum thresholds
- Unit coverage >= 80%
- Critical workflow coverage >= 90%

### Additional expectations
- branch coverage phải tốt ở các path quan trọng,
- failure path không được bỏ qua,
- exception path phải có test.

## 5. Test structure

### 5.1. Folder organization

```text
tests/
├── unit/
├── integration/
├── workflow/
├── prompt/
└── chaos/
```

### 5.2. Naming conventions
- Unit tests: `test_<module>.py`
- Workflow tests: `test_<workflow_id>.py`
- Prompt tests: `test_<prompt_name>.py`
- Integration tests: `test_<component_a>_<component_b>.py`
- Chaos tests: `test_<failure_mode>.py`

## 6. Fixture and mock rules

- Fixture phải nhỏ gọn và rõ ý nghĩa.
- Mock chỉ dùng ở boundary cần thiết.
- Không mock quá sâu đến mức test không còn ý nghĩa.
- External dependencies phải được mock hoặc sandbox hóa.
- Không dùng real network trừ khi test được đánh dấu rõ là integration với môi trường thật.

## 7. Regression rules

- Mỗi lỗi đã sửa phải có test riêng để không tái diễn.
- Nếu thay đổi contract, phải cập nhật test tương ứng.
- Nếu thay đổi behavior, phải kiểm tra tác động đến workflow test và prompt evaluation.

## 8. Test data rules

- Test data phải versioned nếu nó là golden dataset.
- Không dùng dữ liệu thật chứa thông tin nhạy cảm.
- Dữ liệu test phải đủ nhỏ để chạy nhanh.
- Có thể tạo synthetic data nếu giúp test rõ hơn.

## 9. Workflow test expectations

Workflow test phải xác nhận:
- workflow load được,
- DAG được build đúng,
- task chạy đúng thứ tự,
- output đúng schema,
- lineage được ghi,
- decision engine trả kết quả đúng,
- failure path hoạt động đúng.

## 10. Prompt evaluation expectations

Prompt evaluation phải kiểm tra:
- output format,
- required fields,
- completeness,
- deterministic structure,
- tolerance cho semantic variation nếu được phép.

## 11. Chaos test expectations

Chaos test phải mô phỏng:
- mất kết nối storage,
- timeout external API,
- lỗi filesystem,
- lỗi dependency,
- rollback boundary.

Kết quả mong đợi:
- fail fast khi cần,
- rollback đúng policy,
- error được ghi nhận,
- hệ thống không bị corrupted state.

## 12. CI rules

- Unit test phải chạy trên mỗi commit.
- Integration và workflow test phải chạy trên merge gate.
- Prompt evaluation và chaos test có thể chạy theo schedule hoặc release gate.
- Không cho merge nếu test bắt buộc fail.

## 13. Claude implementation instruction

Khi Claude viết test cho HMIP:
- viết test theo contract, không chỉ theo implementation detail,
- ưu tiên test boundary quan trọng,
- mỗi module sinh ra phải có test tương ứng,
- không bỏ qua failure path,
- luôn thêm regression test khi sửa lỗi.