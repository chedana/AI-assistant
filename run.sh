#!/usr/bin/env bash
set -euo pipefail

# Prefer RunPod workspace path; fall back to script directory.
APP_DIR="/workspace/AI-assistant"
if [[ ! -d "${APP_DIR}" ]]; then
  APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

cd "${APP_DIR}"

# Qdrant
export RENT_QDRANT_PATH="${RENT_QDRANT_PATH:-/workspace/AI-assistant/artifacts/skills/search/data/qdrant_local}"
export RENT_QDRANT_COLLECTION="${RENT_QDRANT_COLLECTION:-rent_listings}"
export RENT_QDRANT_ENABLE_PREFILTER="${RENT_QDRANT_ENABLE_PREFILTER:-1}"
export RENT_PREF_VECTOR_PATH="${RENT_PREF_VECTOR_PATH:-/workspace/AI-assistant/artifacts/skills/search/data/features/pref_vectors.parquet}"
export RENT_STAGEA_TRACE="0"
export RENT_LOCATION_DEBUG_PRINT="0"
export RENT_STRUCTURED_DEBUG_PRINT="${RENT_STRUCTURED_DEBUG_PRINT:-0}"

# Retrieval / structured policy
export RENT_RECALL="${RENT_RECALL:-1000}"
export RENT_STRUCTURED_POLICY="${RENT_STRUCTURED_POLICY:-RULE_FIRST}"
export RENT_STRUCTURED_CONFLICT_LOG="${RENT_STRUCTURED_CONFLICT_LOG:-1}"
export RENT_STRUCTURED_CONFLICT_LOG_PATH="${RENT_STRUCTURED_CONFLICT_LOG_PATH:-/workspace/AI-assistant/artifacts/skills/search/logs/structured_conflicts.jsonl}"
export RENT_STRUCTURED_TRAINING_LOG_PATH="${RENT_STRUCTURED_TRAINING_LOG_PATH:-/workspace/AI-assistant/artifacts/skills/search/logs/structured_training_samples.jsonl}"
export RENT_ENABLE_STAGE_D_EXPLAIN="${RENT_ENABLE_STAGE_D_EXPLAIN:-1}"
export ROUTER_DEBUG="${ROUTER_DEBUG:-0}"

# LLM endpoints/models
# Reasoning model (search extraction / QA / explanation)
export QWEN_BASE_URL="${QWEN_BASE_URL:-http://127.0.0.1:8002/v1}"
export QWEN_MODEL="${QWEN_MODEL:-Qwen3-8B}"
# Router model (intent classification) defaults to same as reasoning model.
export ROUTER_BASE_URL="${ROUTER_BASE_URL:-${QWEN_BASE_URL}}"
export ROUTER_MODEL="${ROUTER_MODEL:-${QWEN_MODEL}}"
# API keys (Router falls back to OPENAI_API_KEY if ROUTER_API_KEY is unset)
export OPENAI_API_KEY="${OPENAI_API_KEY:-dummy}"
export ROUTER_API_KEY="${ROUTER_API_KEY:-${OPENAI_API_KEY}}"

mkdir -p "/workspace/AI-assistant/artifacts/skills/search/logs" || true

echo "[run] APP_DIR=${APP_DIR}"
echo "[run] RENT_QDRANT_PATH=${RENT_QDRANT_PATH}"
echo "[run] RENT_QDRANT_COLLECTION=${RENT_QDRANT_COLLECTION}"
echo "[run] RENT_QDRANT_ENABLE_PREFILTER=${RENT_QDRANT_ENABLE_PREFILTER}"
echo "[run] RENT_PREF_VECTOR_PATH=${RENT_PREF_VECTOR_PATH}"
echo "[run] RENT_STAGEA_TRACE=${RENT_STAGEA_TRACE}"
echo "[run] RENT_LOCATION_DEBUG_PRINT=${RENT_LOCATION_DEBUG_PRINT}"
echo "[run] RENT_STRUCTURED_DEBUG_PRINT=${RENT_STRUCTURED_DEBUG_PRINT}"
echo "[run] RENT_RECALL=${RENT_RECALL}"
echo "[run] RENT_STRUCTURED_POLICY=${RENT_STRUCTURED_POLICY}"
echo "[run] RENT_STRUCTURED_CONFLICT_LOG=${RENT_STRUCTURED_CONFLICT_LOG}"
echo "[run] RENT_STRUCTURED_CONFLICT_LOG_PATH=${RENT_STRUCTURED_CONFLICT_LOG_PATH}"
echo "[run] RENT_STRUCTURED_TRAINING_LOG_PATH=${RENT_STRUCTURED_TRAINING_LOG_PATH}"
echo "[run] RENT_ENABLE_STAGE_D_EXPLAIN=${RENT_ENABLE_STAGE_D_EXPLAIN}"
echo "[run] ROUTER_DEBUG=${ROUTER_DEBUG}"
echo "[run] QWEN_BASE_URL=${QWEN_BASE_URL}"
echo "[run] QWEN_MODEL=${QWEN_MODEL}"
echo "[run] ROUTER_BASE_URL=${ROUTER_BASE_URL}"
echo "[run] ROUTER_MODEL=${ROUTER_MODEL}"

exec python3 main.py
