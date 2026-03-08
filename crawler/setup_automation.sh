#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  setup_automation.sh — Install/uninstall launchd schedule
#
#  Creates a macOS LaunchAgent that runs auto_crawl.sh:
#    - On schedule: Monday + Thursday at 3:00 AM
#    - On demand: when the trigger file is created (OpenClaw Discord)
#
#  Usage:
#    bash crawler/setup_automation.sh install    # create + load plist
#    bash crawler/setup_automation.sh uninstall  # unload + remove plist
#    bash crawler/setup_automation.sh status     # show state + last 10 log lines
# ══════════════════════════════════════════════════════════════════

set -euo pipefail

LABEL="com.openclaw.crawl"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
AUTO_CRAWL="${SCRIPT_DIR}/auto_crawl.sh"
LOG_FILE="${SCRIPT_DIR}/artifacts/crawl_automation.log"
VENV_PYTHON="${PROJECT_ROOT}/../openclaw-venv/bin/python3"

# OpenClaw config dir (bind-mounted into Docker container)
OPENCLAW_CONFIG="${HOME}/openclaw-secure/config"
TRIGGER_FILE="${OPENCLAW_CONFIG}/crawl-trigger"
STATUS_FILE="${OPENCLAW_CONFIG}/crawl-status.json"

# Detect Playwright browser path
if [[ -d "${HOME}/Library/Caches/ms-playwright" ]]; then
    PW_BROWSERS="${HOME}/Library/Caches/ms-playwright"
elif [[ -n "${PLAYWRIGHT_BROWSERS_PATH:-}" ]]; then
    PW_BROWSERS="${PLAYWRIGHT_BROWSERS_PATH}"
else
    PW_BROWSERS="${HOME}/Library/Caches/ms-playwright"
fi

cmd_install() {
    echo "Installing launchd agent: ${LABEL}"

    if [[ ! -f "${AUTO_CRAWL}" ]]; then
        echo "[ERROR] auto_crawl.sh not found at ${AUTO_CRAWL}"
        exit 1
    fi

    mkdir -p "$(dirname "${PLIST_PATH}")"
    mkdir -p "$(dirname "${LOG_FILE}")"

    # Build PATH that includes Homebrew + venv
    LAUNCH_PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    if [[ -x "${VENV_PYTHON}" ]]; then
        VENV_BIN="$(dirname "${VENV_PYTHON}")"
        LAUNCH_PATH="${VENV_BIN}:${LAUNCH_PATH}"
    fi

    cat > "${PLIST_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${AUTO_CRAWL}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${LAUNCH_PATH}</string>
        <key>PLAYWRIGHT_BROWSERS_PATH</key>
        <string>${PW_BROWSERS}</string>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>TRIGGER_FILE</key>
        <string>${TRIGGER_FILE}</string>
        <key>STATUS_FILE</key>
        <string>${STATUS_FILE}</string>
    </dict>

    <key>StartCalendarInterval</key>
    <array>
        <!-- Monday 3:00 AM -->
        <dict>
            <key>Weekday</key>
            <integer>1</integer>
            <key>Hour</key>
            <integer>3</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- Thursday 3:00 AM -->
        <dict>
            <key>Weekday</key>
            <integer>4</integer>
            <key>Hour</key>
            <integer>3</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>

    <!-- Also trigger when OpenClaw agent creates the trigger file -->
    <key>WatchPaths</key>
    <array>
        <string>${TRIGGER_FILE}</string>
    </array>

    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

    echo "  Plist written to ${PLIST_PATH}"

    # Unload first if already loaded (ignore errors)
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true

    # Load the agent
    launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
    echo "  Agent loaded."
    echo ""
    echo "Schedule: Monday + Thursday at 3:00 AM"
    echo "On-demand trigger: touch ${TRIGGER_FILE}"
    echo "Status file: ${STATUS_FILE}"
    echo "Log: ${LOG_FILE}"
    echo ""
    echo "To run immediately:"
    echo "  launchctl kickstart gui/$(id -u)/${LABEL}"
}

cmd_uninstall() {
    echo "Uninstalling launchd agent: ${LABEL}"

    # Unload
    if launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null; then
        echo "  Agent unloaded."
    else
        echo "  Agent was not loaded (already stopped)."
    fi

    # Remove plist
    if [[ -f "${PLIST_PATH}" ]]; then
        rm "${PLIST_PATH}"
        echo "  Plist removed: ${PLIST_PATH}"
    else
        echo "  No plist found at ${PLIST_PATH}"
    fi

    echo "Done."
}

cmd_status() {
    echo "═══════════════════════════════════════════"
    echo "  LaunchAgent: ${LABEL}"
    echo "═══════════════════════════════════════════"

    if [[ -f "${PLIST_PATH}" ]]; then
        echo "  Plist:   ${PLIST_PATH} (exists)"
    else
        echo "  Plist:   NOT INSTALLED"
    fi

    echo ""
    echo "  launchctl status:"
    if launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | head -5; then
        :
    else
        echo "  (not loaded)"
    fi

    echo ""
    if [[ -f "${STATUS_FILE}" ]]; then
        echo "  Last crawl status:"
        cat "${STATUS_FILE}"
        echo ""
    fi

    echo ""
    echo "  Last 10 log lines:"
    if [[ -f "${LOG_FILE}" ]]; then
        tail -10 "${LOG_FILE}"
    else
        echo "  (no log file yet)"
    fi
}

# ── Main ─────────────────────────────────────────────────────────
case "${1:-}" in
    install)   cmd_install ;;
    uninstall) cmd_uninstall ;;
    status)    cmd_status ;;
    *)
        echo "Usage: bash $(basename "$0") {install|uninstall|status}"
        exit 1
        ;;
esac
