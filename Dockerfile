# Dockerfile — HMIP Market Intelligence Platform
# Chạy web app + auto-scan trong 1 container. KHÔNG sửa code gốc.
FROM python:3.13-slim

# Cài build deps (cần cho một số gói) rồi dọn sạch để image nhẹ.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy trước để tận dụng layer cache: chỉ cài lại khi deps đổi.
COPY pyproject.toml ./
COPY extensions ./extensions
COPY core ./core
COPY shared ./shared
COPY platform_ ./platform_
COPY domains ./domains
COPY knowledge ./knowledge
COPY start.sh ./

# Cài package ở editable mode + deps web (fastapi/uvicorn/apscheduler/httpx).
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]" && \
    pip install --no-cache-dir "fastapi" "uvicorn[standard]" "apscheduler" "httpx" "requests"

# Dữ liệu bền vực: volume gắn tại /app/data
ENV HMIP_DB_PATH=/app/data/hmip.db
ENV HMIP_IN_DOCKER=1
ENV HMIP_AUTOSCAN=${HMIP_AUTOSCAN:-on}
ENV HMIP_SCAN_INTERVAL_MIN=${HMIP_SCAN_INTERVAL_MIN:-30}
ENV HMIP_COLLECT_MODE=${HMIP_COLLECT_MODE:-demo}
VOLUME ["/app/data"]

EXPOSE 8000

# start.sh tạo venv-app, cài deps, chạy uvicorn. Ở container ta đã cài sẵn
# nên start.sh sẽ phát hiện venv-app tồn tại và chỉ chạy uvicorn.
CMD ["./start.sh", "--port", "8000"]
