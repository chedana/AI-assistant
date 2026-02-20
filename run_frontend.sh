#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/workspace/AI-assistant"
if [[ ! -d "${APP_DIR}" ]]; then
  APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

FRONTEND_DIR="${APP_DIR}/frontend"
if [[ ! -d "${FRONTEND_DIR}" ]]; then
  echo "[frontend][error] frontend directory not found: ${FRONTEND_DIR}"
  exit 1
fi

export NVM_DIR="${HOME}/.nvm"
if [[ -s "${NVM_DIR}/nvm.sh" ]]; then
  # shellcheck source=/dev/null
  source "${NVM_DIR}/nvm.sh"
else
  echo "[frontend][error] nvm not found at ${NVM_DIR}/nvm.sh"
  echo "[frontend][hint] install nvm first, then run this script again."
  exit 1
fi

nvm use 20 >/dev/null 2>&1 || nvm install 20 >/dev/null
nvm use 20 >/dev/null

cd "${FRONTEND_DIR}"

if [[ ! -d "node_modules" ]]; then
  echo "[frontend] node_modules not found, running npm install..."
  npm install
fi

echo "[frontend] starting vite on 0.0.0.0:5173"
exec npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
