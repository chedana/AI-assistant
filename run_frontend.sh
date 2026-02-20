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
NVM_CANDIDATES=(
  "${NVM_DIR}"
  "${HOME}/.nvm"
  "/root/.nvm"
)

for d in /home/*/.nvm; do
  if [[ -d "${d}" ]]; then
    NVM_CANDIDATES+=("${d}")
  fi
done

NVM_FOUND=""
for d in "${NVM_CANDIDATES[@]}"; do
  if [[ -s "${d}/nvm.sh" ]]; then
    NVM_FOUND="${d}"
    break
  fi
done

if [[ -z "${NVM_FOUND}" ]]; then
  echo "[frontend] nvm not found, installing nvm..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  else
    echo "[frontend][error] neither curl nor wget is available, cannot install nvm automatically."
    exit 1
  fi

  NVM_CANDIDATES=(
    "${HOME}/.nvm"
    "/root/.nvm"
  )
  for d in /home/*/.nvm; do
    if [[ -d "${d}" ]]; then
      NVM_CANDIDATES+=("${d}")
    fi
  done
  for d in "${NVM_CANDIDATES[@]}"; do
    if [[ -s "${d}/nvm.sh" ]]; then
      NVM_FOUND="${d}"
      break
    fi
  done
  if [[ -z "${NVM_FOUND}" ]]; then
    echo "[frontend][error] nvm install finished but nvm.sh was not found."
    exit 1
  fi
fi

export NVM_DIR="${NVM_FOUND}"
# shellcheck source=/dev/null
source "${NVM_DIR}/nvm.sh"

nvm use 20 >/dev/null 2>&1 || nvm install 20 >/dev/null
nvm use 20 >/dev/null

cd "${FRONTEND_DIR}"

if [[ ! -d "node_modules" ]]; then
  echo "[frontend] node_modules not found, running npm install..."
  npm install
fi

echo "[frontend] starting vite on 0.0.0.0:5173"
exec npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
