#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/workspace/AI-assistant"
if [[ ! -d "${APP_DIR}" ]]; then
  APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

BACKEND_DIR="${APP_DIR}/backend"
if [[ ! -d "${BACKEND_DIR}" ]]; then
  echo "[backend][error] backend directory not found: ${BACKEND_DIR}"
  exit 1
fi

# Prefer existing RunPod venv if available.
if [[ -f "/workspace/chat_bot/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source /workspace/chat_bot/bin/activate
fi

cd "${APP_DIR}"

if [[ ! -f "${BACKEND_DIR}/requirements.txt" ]]; then
  echo "[backend][error] requirements file not found: ${BACKEND_DIR}/requirements.txt"
  exit 1
fi

echo "[backend] installing dependencies from backend/requirements.txt ..."
python3 -m pip install -r "${BACKEND_DIR}/requirements.txt"

export PYTHONPATH="${APP_DIR}:${PYTHONPATH:-}"
export QWEN_BASE_URL="${QWEN_BASE_URL:-http://127.0.0.1:8002/v1}"
export ROUTER_BASE_URL="${ROUTER_BASE_URL:-${QWEN_BASE_URL}}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-dummy}"
export ROUTER_API_KEY="${ROUTER_API_KEY:-${OPENAI_API_KEY}}"

echo "[backend] starting uvicorn on 0.0.0.0:8000"
exec uvicorn backend.api_server:app --host 0.0.0.0 --port 8000
