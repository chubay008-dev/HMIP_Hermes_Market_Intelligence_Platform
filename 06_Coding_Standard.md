# HMIP — Coding Standard

## 1. Mục tiêu

Tài liệu này quy định các chuẩn mã nguồn bắt buộc cho toàn bộ hệ thống HMIP. Mục tiêu là đảm bảo code do Claude hoặc con người sinh ra có tính nhất quán, dễ bảo trì, dễ kiểm thử, và phù hợp với kiến trúc enterprise của HMIP.

## 2. Ngôn ngữ và phiên bản

- Ngôn ngữ chính: Python
- Phiên bản Python: 3.12
- Không sử dụng features không tương thích với Python 3.12 nếu chưa được chốt rõ trong spec.

## 3. Công cụ bắt buộc

- Formatter: `ruff format`
- Linter: `ruff`
- Type checker: `mypy` với chế độ strict
- Test runner: `pytest`
- Dependency manager: `uv`
- Optional runtime typing helpers: `pydantic v2` nếu cần schema validation

## 4. Nguyên tắc mã nguồn

- Code phải rõ ràng, ưu tiên dễ đọc hơn là ngắn gọn cực đoan.
- Không viết code mơ hồ hoặc “magic”.
- Không dùng global state trừ khi spec cho phép rõ ràng.
- Không dùng singleton pattern nếu không có lý do kiến trúc rất rõ.
- Ưu tiên dependency injection thay vì hardcode phụ thuộc.
- Mỗi module chỉ nên có một trách nhiệm chính.
- Business logic phải nằm trong domain layer, không đặt trong core runtime.
- Mọi side effect phải được cô lập qua adapter, service hoặc interface.

## 5. Kiểu dữ liệu và typing

- Tất cả public function, method, class property phải có type hints.
- Không bỏ qua kiểu trả về.
- Ưu tiên immutable data structures khi phù hợp.
- Dùng `dataclass(frozen=True)` hoặc `pydantic.BaseModel` cho các object contract quan trọng.
- Không dùng `Any` trừ khi bất khả kháng; nếu dùng phải có ghi chú lý do.
- Tất cả type narrowing phải rõ ràng và an toàn.

## 6. Naming conventions

### 6.1. Package và module
- Package name: lowercase
- Module name: snake_case
- Tránh viết tắt mơ hồ.

### 6.2. Class names
- Dùng PascalCase.

### 6.3. Function và method names
- Dùng snake_case.
- Tên phải diễn đạt hành động rõ ràng.

### 6.4. Constants
- Dùng UPPER_SNAKE_CASE.

## 7. Import rules

- Import theo thứ tự:
  1. standard library
  2. third-party
  3. local imports
- Không dùng wildcard import.
- Không tạo circular import nếu tránh được.
- Nếu cần phá circular import, phải thiết kế lại interface trước.

## 8. Error handling

- Không nuốt exception một cách im lặng.
- Mọi exception trong core module phải có class rõ ràng.
- Chỉ catch exception cụ thể khi có lý do.
- Không dùng `except Exception` trừ khi ở boundary layer và có ghi nhận rõ.
- Error message phải có ngữ cảnh, không chỉ là câu chung chung.
- Exception nên mang theo code hoặc metadata nếu cần audit.

## 9. Logging

- Dùng structured logging.
- Ưu tiên `structlog` hoặc equivalent.
- Không log secret, token, password, private key, hoặc dữ liệu nhạy cảm.
- Log message phải ngắn, rõ, có ngữ cảnh vận hành.
- Mọi log quan trọng phải có `execution_id` và `trace_id` nếu có.

## 10. Async rules

- Chỉ dùng `asyncio` nếu có lợi ích rõ ràng về I/O concurrency.
- Không trộn async và sync tùy tiện trong cùng một flow.
- Nếu một module async, boundary và interface phải được thiết kế nhất quán.
- Không tạo event loop thủ công nếu không cần thiết.

## 11. Dependency injection

- Dependency injection là mặc định.
- Core services, adapters, repositories, clients phải được inject qua constructor hoặc factory.
- Không hardcode external dependency trong business logic.
- Không gọi network, filesystem hoặc secrets provider trực tiếp trong domain logic.

## 12. Config rules

- Config phải đi qua subsystem chuẩn của HMIP.
- Không đọc env var trực tiếp trong business logic nếu có thể tránh.
- Config sau bootstrap phải immutable.
- Secret values phải được resolve qua secret handles hoặc provider abstraction.

## 13. Domain rules

- Domain layer chứa business logic thực sự.
- Core layer không chứa rule nghiệp vụ cụ thể như pricing, anomaly detection, competitor watch.
- Prompt, skill, schema, workflow liên quan đến domain phải đặt trong domain pack tương ứng.
- Domain code phải được tổ chức theo vertical slice.

## 14. Adapter rules

- Adapter chỉ làm nhiệm vụ tích hợp hệ thống ngoài.
- Adapter không được chứa logic quyết định nghiệp vụ.
- Adapter phải có timeout, retry, và failure handling rõ ràng.
- Adapter phải dễ mock trong test.

## 15. Validation rules

- Tất cả input quan trọng phải được validate ở boundary.
- Schema validation phải rõ ràng và test được.
- Không để dữ liệu không hợp lệ đi sâu vào workflow engine.
- Nếu dữ liệu không hợp lệ, phải fail fast hoặc chuyển sang escalation theo policy.

## 16. Test rules

- Mọi public behavior phải có test.
- Mọi bug được sửa phải có regression test.
- Test unit phải nhỏ, nhanh, deterministic.
- Integration test phải kiểm tra boundary thật sự quan trọng.
- Workflow test phải phản ánh end-to-end behavior.
- Prompt evaluation test phải dùng golden dataset hoặc expected output set.
- Chaos/fault injection test chỉ áp dụng ở các boundary thích hợp.

## 17. File size and structure

- Một file nên có trách nhiệm rõ ràng.
- Không để file quá lớn nếu có thể tách.
- Tránh “god module”.
- Nếu một module vượt quá phạm vi rõ ràng, phải tách thành submodules.

## 18. Comments and documentation

- Code phải tự giải thích được phần lớn thông qua naming và structure.
- Chỉ dùng comment khi thật sự cần giải thích intent hoặc constraint.
- Không viết comment lặp lại code.
- Public module, class, function quan trọng phải có docstring ngắn gọn và rõ ràng.

## 19. Forbidden patterns

- Global mutable state.
- Hidden side effects.
- Magic numbers không giải thích.
- Hardcoded secrets.
- Deeply nested logic khó đọc.
- Business logic trong platform hoặc core runtime nếu không thuộc trách nhiệm.
- Tạo interface không cần thiết chỉ để trông “enterprise”.

## 20. Recommended patterns

- Dataclass hoặc Pydantic model cho data contract.
- Factory cho object creation phức tạp.
- Strategy pattern cho policy hoặc decision rules.
- Adapter pattern cho external integration.
- Dependency injection cho services.
- Explicit error types cho control flow quan trọng.

## 21. Review gate

Mỗi pull request hoặc code change phải đạt:
- Ruff pass.
- Mypy pass.
- Pytest pass.
- Không vi phạm folder responsibility.
- Không vi phạm architecture boundary.
- Không thay đổi contract mà không cập nhật spec tương ứng.

## 22. Claude implementation instruction

Khi Claude sinh code cho HMIP:
- ưu tiên rõ ràng hơn tối ưu hóa sớm,
- tuân thủ folder structure,
- không tự ý đổi contract,
- không tự ý thêm framework mới,
- nếu thiếu thông tin, hãy liệt kê câu hỏi trước thay vì đoán,
- tạo test đi kèm với implementation,
- giữ code consistent với các chuẩn trên.