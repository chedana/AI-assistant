#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  auto_crawl.sh — Automated crawl + sync + purge + cleanup
#
#  Sources .env, runs each step independently (one failure doesn't
#  block the rest), logs to crawler/artifacts/crawl_automation.log
#  with 10MB rotation.
#
#  Env vars for OpenClaw integration:
#    TRIGGER_FILE  — if set, removed at start (launchd WatchPaths trigger)
#    STATUS_FILE   — if set, writes JSON status summary at end
#
#  Usage:
#    bash crawler/auto_crawl.sh          # run from project root
#    bash auto_crawl.sh                  # run from crawler/
# ══════════════════════════════════════════════════════════════════

set -uo pipefail

# ── Paths ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
LOG_FILE="${SCRIPT_DIR}/artifacts/crawl_automation.log"
LOG_MAX_BYTES=10485760  # 10MB

# How many days before a listing is considered stale
PURGE_DAYS="${PURGE_DAYS:-30}"
# How many old run directories to keep (newest N kept)
KEEP_RUNS="${KEEP_RUNS:-5}"

# ── Remove trigger file (OpenClaw WatchPaths integration) ────────
if [[ -n "${TRIGGER_FILE:-}" && -f "${TRIGGER_FILE}" ]]; then
    rm -f "${TRIGGER_FILE}"
fi

# ── Log rotation ─────────────────────────────────────────────────
mkdir -p "$(dirname "${LOG_FILE}")"
if [[ -f "${LOG_FILE}" ]]; then
    log_size=$(stat -f%z "${LOG_FILE}" 2>/dev/null || stat -c%s "${LOG_FILE}" 2>/dev/null || echo 0)
    if (( log_size > LOG_MAX_BYTES )); then
        mv "${LOG_FILE}" "${LOG_FILE}.1"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log rotated (was ${log_size} bytes)" > "${LOG_FILE}"
    fi
fi

# ── Logging helper ───────────────────────────────────────────────
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

log "════════════════════════════════════════════════════════════"
log "  auto_crawl.sh started"
log "════════════════════════════════════════════════════════════"

# ── Source .env ──────────────────────────────────────────────────
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
    log "Loaded .env from ${ENV_FILE}"
else
    log "[WARN] No .env found at ${ENV_FILE} — relying on existing env"
fi

# ── Python ───────────────────────────────────────────────────────
PYTHON="${PROJECT_ROOT}/../openclaw-venv/bin/python3"
if [[ ! -x "${PYTHON}" ]]; then
    PYTHON="$(command -v python3)"
fi
log "Using Python: ${PYTHON}"

EXIT_CODE=0
STEP_RESULTS=""

# ── Step 1: Crawl Rightmove ─────────────────────────────────────
log "── Step 1: Crawl Rightmove ──"
if "${PYTHON}" "${SCRIPT_DIR}/crawl_london.py" \
    --max-pages 42 --workers 8 --chunk-size 200 --sleep-sec 0.5 \
    >> "${LOG_FILE}" 2>&1; then
    log "Step 1 OK: Crawl completed"
    STEP_RESULTS="${STEP_RESULTS}\"crawl\": \"ok\", "
else
    log "[ERROR] Step 1 FAILED: Crawl (exit $?)"
    EXIT_CODE=1
    STEP_RESULTS="${STEP_RESULTS}\"crawl\": \"failed\", "
fi

# ── Step 2: Incremental sync to Qdrant ──────────────────────────
log "── Step 2: Sync to Qdrant Cloud ──"
if "${PYTHON}" "${SCRIPT_DIR}/sync_qdrant.py" --mode sync \
    >> "${LOG_FILE}" 2>&1; then
    log "Step 2 OK: Sync completed"
    STEP_RESULTS="${STEP_RESULTS}\"sync\": \"ok\", "
else
    log "[ERROR] Step 2 FAILED: Sync (exit $?)"
    EXIT_CODE=1
    STEP_RESULTS="${STEP_RESULTS}\"sync\": \"failed\", "
fi

# ── Step 3: Purge stale listings ────────────────────────────────
log "── Step 3: Purge stale listings (${PURGE_DAYS} days) ──"
if "${PYTHON}" "${SCRIPT_DIR}/sync_qdrant.py" --purge-days "${PURGE_DAYS}" \
    >> "${LOG_FILE}" 2>&1; then
    log "Step 3 OK: Purge completed"
    STEP_RESULTS="${STEP_RESULTS}\"purge\": \"ok\", "
else
    log "[ERROR] Step 3 FAILED: Purge (exit $?)"
    EXIT_CODE=1
    STEP_RESULTS="${STEP_RESULTS}\"purge\": \"failed\", "
fi

# ── Step 4: Cleanup old run directories ─────────────────────────
log "── Step 4: Cleanup old runs (keeping newest ${KEEP_RUNS}) ──"
RUNS_DIR="${SCRIPT_DIR}/artifacts/runs"
if [[ -d "${RUNS_DIR}" ]]; then
    # List run_* dirs sorted oldest first, remove all but newest KEEP_RUNS
    run_count=$(find "${RUNS_DIR}" -maxdepth 1 -type d -name 'run_*' | wc -l | tr -d ' ')
    if (( run_count > KEEP_RUNS )); then
        to_delete=$(( run_count - KEEP_RUNS ))
        # shellcheck disable=SC2012
        ls -dt "${RUNS_DIR}"/run_* | tail -n "${to_delete}" | while read -r old_run; do
            rm -rf "${old_run}"
            log "  Removed old run: $(basename "${old_run}")"
        done
        log "Step 4 OK: Removed ${to_delete} old run(s)"
        STEP_RESULTS="${STEP_RESULTS}\"cleanup\": \"ok, removed ${to_delete}\", "
    else
        log "Step 4 OK: Only ${run_count} run(s), nothing to clean"
        STEP_RESULTS="${STEP_RESULTS}\"cleanup\": \"ok, nothing to clean\", "
    fi
else
    log "Step 4 SKIP: No runs directory"
    STEP_RESULTS="${STEP_RESULTS}\"cleanup\": \"skipped\", "
fi

# ── Done ─────────────────────────────────────────────────────────
FINISHED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
if (( EXIT_CODE == 0 )); then
    log "All steps completed successfully."
    OVERALL="success"
else
    log "Finished with errors (exit code ${EXIT_CODE})."
    OVERALL="partial_failure"
fi

# ── Write status JSON (for OpenClaw skill to read) ──────────────
if [[ -n "${STATUS_FILE:-}" ]]; then
    cat > "${STATUS_FILE}" <<STATUSEOF
{"status": "${OVERALL}", "finished_at": "${FINISHED_AT}", ${STEP_RESULTS}"exit_code": ${EXIT_CODE}}
STATUSEOF
    log "Status written to ${STATUS_FILE}"
fi

log "════════════════════════════════════════════════════════════"
exit ${EXIT_CODE}
