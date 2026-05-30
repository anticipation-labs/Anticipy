#!/usr/bin/env bash
# Long-running daemon. Calls tools/anticipy_loop_sentinel.sh every
# 180 seconds. Kill switch: touch ~/.anticipy/.sentinel_off and the
# next loop iteration exits cleanly with code 0.
#
# Operator activates this script. Sentinel does NOT auto-load itself.
# Examples:
#   nohup tools/anticipy_loop_sentinel_runner.sh \
#     >> state/orchestrator/sentinel_runner.out 2>&1 &
# OR via launchd (plist created by operator; this script just runs).

set -u

REPO_ROOT="${ANTICIPY_REPO_ROOT:-/Users/omarebrahim/Developer/Anticipy-V7}"
ITER_SCRIPT="${REPO_ROOT}/tools/anticipy_loop_sentinel.sh"
KILL_SWITCH="${HOME}/.anticipy/.sentinel_off"
INTERVAL_SECONDS="${SENTINEL_INTERVAL_SECONDS:-180}"
LOG_FILE="${REPO_ROOT}/state/orchestrator/sentinel.log"

mkdir -p "$(dirname "${LOG_FILE}")"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
runner_log() { printf "[%s] runner: %s\n" "$(ts)" "$1" >> "${LOG_FILE}"; }

runner_log "starting; interval=${INTERVAL_SECONDS}s kill-switch=${KILL_SWITCH}"

while true; do
  if [ -e "${KILL_SWITCH}" ]; then
    runner_log "kill-switch present at ${KILL_SWITCH}; exiting"
    exit 0
  fi
  if [ ! -x "${ITER_SCRIPT}" ]; then
    runner_log "iter script not executable: ${ITER_SCRIPT}; sleeping"
  else
    "${ITER_SCRIPT}" || runner_log "iter exited non-zero (RED)"
  fi
  sleep "${INTERVAL_SECONDS}"
done
