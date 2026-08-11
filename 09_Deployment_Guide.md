# HMIP — Deployment Guide

## 1. Mục tiêu

Tài liệu này quy định cách build, chạy, kiểm tra và triển khai HMIP trong môi trường local và enterprise. Mục tiêu là giúp Claude sinh ra hệ thống có thể chạy được, đóng gói được, và vận hành được một cách nhất quán.

## 2. Deployment principles

- Build phải reproducible.
- Runtime phải có startup command rõ ràng.
- Config phải được inject theo environment.
- Secrets không được hardcode trong image hoặc repo.
- Container phải fail fast nếu bootstrap thất bại.
- Healthcheck và readiness check phải rõ ràng.
- Deployment phải tách biệt giữa local, staging và production.

## 3. Runtime prerequisites

- Python 3.12
- Dependencies được pin rõ ràng
- uv để quản lý package
- ruff và mypy trong pipeline
- pytest cho test
- Playwright và system dependencies nếu có scraping browser-based

## 4. Local development setup

### Required steps
1. Clone repository.
2. Create virtual environment hoặc dùng uv.
3. Install dependencies.
4. Configure environment variables.
5. Run bootstrap.
6. Run tests.
7. Run workflow locally.

### Suggested command
```bash
python -m hmip.platform.bootstrap
```

## 5. Environment variables

Tối thiểu cần:
- HMIP_ENV
- HMIP_RUNTIME_VERSION
- HMIP_KERNEL_VERSION
- HMIP_LOG_LEVEL
- HMIP_SECRET_PROVIDER
- HMIP_CONFIG_PATH
- HMIP_DATA_DIR
- HMIP_REPORT_DIR

## 6. Containerization

### Container requirements
- Base image phải phù hợp Python 3.12.
- System dependencies phải được cài rõ nếu workflow cần browser automation.
- Source code phải được copy vào image sau khi cài dependency.
- Bootstrap command phải là entrypoint hoặc command chính.

### Suggested image behavior
- build reproducible,
- small enough nếu có thể,
- không chứa secret,
- không chứa data runtime.

## 7. Startup and shutdown

### Startup
- load env,
- load config,
- initialize logging,
- initialize registry/container,
- register workflows and plugins,
- freeze registry,
- validate runtime,
- start execution plane.

### Shutdown
- flush logs,
- close external clients,
- persist final execution report nếu có,
- release resources theo thứ tự an toàn.

## 8. Health and readiness

### Healthcheck
- kiểm tra process còn sống,
- kiểm tra dependency cơ bản,
- không thực hiện work nặng.

### Readiness
- kiểm tra bootstrap đã hoàn tất,
- registry đã freeze,
- config đã valid,
- runtime sẵn sàng nhận workflow.

## 9. Release process

### Suggested flow
1. Run unit tests.
2. Run integration tests.
3. Run workflow tests.
4. Build container.
5. Run smoke bootstrap.
6. Deploy to staging.
7. Run health/readiness check.
8. Promote to production nếu đạt.

## 10. Operational safety

- Không deploy khi bootstrap fail.
- Không deploy nếu critical tests fail.
- Không deploy khi config drift chưa được giải quyết.
- Không deploy nếu secret provider chưa sẵn sàng.
- Không deploy nếu observability chưa bật.

## 11. Observability in deployment

- Logs phải ra stdout/stderr hoặc hệ thống logging chuẩn.
- Metrics phải có endpoint hoặc export mechanism rõ.
- Trace/lineage phải lưu được cho workflow execution.
- Nếu fail ở bootstrap, phải có report đủ ngữ cảnh để debug.

## 12. Claude implementation instruction

Khi Claude tạo deployment code cho HMIP:
- giữ startup command đơn giản và rõ ràng,
- không hardcode secrets,
- không thêm runtime dependency không cần thiết,
- phải có health/readiness checks,
- container phải phản ánh đúng repository structure và bootstrap flow.