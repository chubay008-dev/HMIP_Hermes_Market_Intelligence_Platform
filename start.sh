#!/usr/bin/env bash
# start.sh — khởi động HMIP Market Intelligence Platform
#
# Dùng:
#   ./start.sh              # chạy web app tại http://127.0.0.1:8000
#   ./start.sh --port 9000  # đổi cổng
#
set -euo pipefail

cd "$(dirname "$0")"

PORT=8000
while [[ $# -gt 0 ]]; do
  case $1 in
    --port) PORT="$2"; shift 2 ;;
    *) echo "Tham số không rõ: $1"; exit 1 ;;
  esac
done

# --- venv -------------------------------------------------------------
# LƯU Ý: .venv/ trong repo là virtualenv Windows (chỉ có Scripts/*.exe),
# không chạy được trên Linux/macOS. Ta dùng .venv-app riêng KHI CHẠY LOCAL.
#
# Trong container Docker, deps đã được cài vào system python ở build time
# → dùng luôn python3, không tạo venv (tránh build lại trong container).
VENV=".venv-app"
PYTHON="python3"
# Nếu đã có venv-app (local) → ưu tiên dùng nó.
if [[ -x "$VENV/bin/python" ]]; then
  PYTHON="$VENV/bin/python"
elif [[ ! -x "$VENV/bin/python" ]] && [[ -z "${HMIP_IN_DOCKER:-}" ]]; then
  echo "→ Tạo virtualenv $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  echo "→ Cài dependencies ..."
  "$VENV/bin/pip" install -q -e ".[dev]"
  "$VENV/bin/pip" install -q fastapi "uvicorn[standard]" httpx
  PYTHON="$VENV/bin/python"
fi

# --- cấu hình ---------------------------------------------------------
export HMIP_DB_PATH="${HMIP_DB_PATH:-hmip.db}"
export HMIP_COLLECT_MODE="${HMIP_COLLECT_MODE:-demo}"

echo
echo "  HMIP — Market Intelligence Platform"
echo "  ───────────────────────────────────────────"
echo "  Web:      http://127.0.0.1:$PORT"
echo "  API docs: http://127.0.0.1:$PORT/docs"
echo "  Database: $HMIP_DB_PATH"
echo "  Nguồn giá: $HMIP_COLLECT_MODE"
echo "  ───────────────────────────────────────────"
echo

# Trong Docker bind 0.0.0.0 để container có thể truy cập từ ngoài.
HOST="127.0.0.1"
if [[ -n "${HMIP_IN_DOCKER:-}" ]]; then
  HOST="0.0.0.0"
fi

exec "$PYTHON" -m uvicorn extensions.api:app --host "$HOST" --port "$PORT"
