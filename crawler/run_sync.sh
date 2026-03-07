#!/usr/bin/env bash
set -euo pipefail

# Usage: bash crawler/run_sync.sh [full|sync|crawl-only]
#   full       = crawl + full Qdrant rebuild
#   sync       = crawl + incremental Qdrant sync (default)
#   crawl-only = crawl only, no Qdrant sync
#
# Required env vars:
#   RENT_QDRANT_URL       Qdrant Cloud cluster URL
#   RENT_QDRANT_API_KEY   Qdrant Cloud API key

MODE="${1:-sync}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${SCRIPT_DIR}"

# Use venv python if available, else fall back to python3
PYTHON="${PROJECT_ROOT}/../openclaw-venv/bin/python3"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3)"
fi

echo "═══════════════════════════════════════════"
echo "  OpenClaw Data Sync — mode: ${MODE}"
echo "═══════════════════════════════════════════"

# Step 1: Crawl Rightmove
echo ""
echo "── Step 1: Crawl Rightmove ──"
"${PYTHON}" crawl_london.py

if [[ "${MODE}" == "crawl-only" ]]; then
    echo ""
    echo "Done (crawl-only mode, no Qdrant sync)."
    exit 0
fi

# Step 2: Sync to Qdrant Cloud
echo ""
echo "── Step 2: Sync to Qdrant Cloud ──"

if [[ -z "${RENT_QDRANT_URL:-}" ]]; then
    echo "[ERROR] RENT_QDRANT_URL not set."
    exit 1
fi

if [[ "${MODE}" == "full" ]]; then
    "${PYTHON}" sync_qdrant.py --mode full
else
    "${PYTHON}" sync_qdrant.py --mode sync
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Sync complete."
echo "═══════════════════════════════════════════"
