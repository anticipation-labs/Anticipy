#!/usr/bin/env bash
# Anticipy engine watchdog.
#
# Polls 127.0.0.1:${ANTICIPY_WATCHDOG_PORT:-8731}/health every
# ${ANTICIPY_WATCHDOG_INTERVAL:-30} seconds. After
# ${ANTICIPY_WATCHDOG_FAIL_THRESHOLD:-3} consecutive failures, respawns
# the engine binary at ${ANTICIPY_WATCHDOG_BIN}. Loops forever; launchd
# is responsible for keeping this script alive (KeepAlive=true).
#
# Kill switch: if ${ANTICIPY_WATCHDOG_KILL_SWITCH} exists, the watchdog
# enters idle mode (still polls so logs show it is alive, but never
# respawns). Remove the file to re-arm.
#
# All output goes to stdout (launchd redirects to
# ~/Library/Logs/anticipy-watchdog.log).

set -u

PORT="${ANTICIPY_WATCHDOG_PORT:-8731}"
INTERVAL="${ANTICIPY_WATCHDOG_INTERVAL:-30}"
FAIL_THRESHOLD="${ANTICIPY_WATCHDOG_FAIL_THRESHOLD:-3}"
HEALTH_URL="http://127.0.0.1:${PORT}/health"
HEALTH_TIMEOUT="${ANTICIPY_WATCHDOG_HEALTH_TIMEOUT:-5}"
ENGINE_BIN="${ANTICIPY_WATCHDOG_BIN:-/Applications/Anticipy.app/Contents/MacOS/anticipy-engine}"
KILL_SWITCH="${ANTICIPY_WATCHDOG_KILL_SWITCH:-${HOME}/.anticipy/.watchdog_off}"
ENGINE_LOG_DIR="${ANTICIPY_WATCHDOG_ENGINE_LOG_DIR:-${HOME}/.anticipy}"
ENGINE_LOG="${ENGINE_LOG_DIR}/product-engine.log"
RESPAWN_COOLDOWN="${ANTICIPY_WATCHDOG_RESPAWN_COOLDOWN:-15}"

log() {
  # ISO 8601 timestamp + message, line-buffered for tail -f.
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

probe_health() {
  # curl returns non-zero on connect failure or non-2xx (because of -f).
  # -s silences progress; we also drop stderr because a transient
  # "Couldn't connect" message is already captured by our own log line.
  curl -fsS -m "${HEALTH_TIMEOUT}" -o /dev/null "${HEALTH_URL}" 2>/dev/null
}

kill_switch_active() {
  [[ -e "${KILL_SWITCH}" ]]
}

respawn_engine() {
  if [[ ! -x "${ENGINE_BIN}" ]]; then
    log "respawn: engine binary missing or not executable at ${ENGINE_BIN}; cannot restart"
    return 1
  fi
  mkdir -p "${ENGINE_LOG_DIR}" 2>/dev/null || true
  log "respawn: launching ${ENGINE_BIN} (port=${PORT})"
  # nohup + & so the engine survives this script exiting (it should not,
  # but defense in depth). setsid is Linux-only; on macOS, the
  # disown / nohup combination is enough.
  ANTICIPY_PORT="${PORT}" \
  ANTICIPY_ENGINE_PORT="${PORT}" \
  ANTICIPY_HEADLESS=1 \
    nohup "${ENGINE_BIN}" >> "${ENGINE_LOG}" 2>&1 &
  local spawned_pid=$!
  disown "${spawned_pid}" 2>/dev/null || true
  log "respawn: spawned pid=${spawned_pid}, cooling down ${RESPAWN_COOLDOWN}s before re-probing"
  sleep "${RESPAWN_COOLDOWN}"
}

main() {
  log "watchdog start: port=${PORT} interval=${INTERVAL}s threshold=${FAIL_THRESHOLD} bin=${ENGINE_BIN}"
  log "kill switch: ${KILL_SWITCH} (touch this file to disable respawn)"

  local consecutive_fails=0
  local kill_switch_warned=0

  while :; do
    if kill_switch_active; then
      if [[ "${kill_switch_warned}" -eq 0 ]]; then
        log "kill switch present at ${KILL_SWITCH}; respawn DISABLED (still polling)"
        kill_switch_warned=1
      fi
      consecutive_fails=0
    else
      if [[ "${kill_switch_warned}" -eq 1 ]]; then
        log "kill switch removed; respawn RE-ENABLED"
        kill_switch_warned=0
      fi

      if probe_health; then
        if [[ "${consecutive_fails}" -gt 0 ]]; then
          log "health recovered after ${consecutive_fails} fail(s)"
        fi
        consecutive_fails=0
      else
        consecutive_fails=$((consecutive_fails + 1))
        log "health fail ${consecutive_fails}/${FAIL_THRESHOLD} for ${HEALTH_URL}"
        if [[ "${consecutive_fails}" -ge "${FAIL_THRESHOLD}" ]]; then
          respawn_engine
          consecutive_fails=0
        fi
      fi
    fi

    sleep "${INTERVAL}"
  done
}

main "$@"
