#!/usr/bin/env bash
# V7 Stranger Batch Supervisor
#
# Wraps scripts/v7/run_until_100.sh in a watchdog that restarts on death.
# Race-tolerant: if another run_until_100 process is already alive (e.g. the
# master supervisor's loop_strangers child), this script attaches as a monitor
# rather than spawning a second loop. When the existing batch exits, this
# supervisor takes over and restarts it.
#
# Stops when:
#   - successful_interactions >= TARGET (default 100)
#   - restart count >= MAX_RESTARTS (default 10)
#   - tasks/stranger_batch_supervisor.stop exists
#
# Usage:
#   nohup bash scripts/v7/stranger_batch_supervisor.sh > /tmp/stranger_supervisor.log 2>&1 &
#
# Env:
#   TARGET         default 100
#   MAX_RESTARTS   default 10
#   COOL_DOWN_SEC  default 60

set -u

REPO="${REPO:-/Users/omarebrahim/Developer/Anticipy-V7}"
cd "$REPO"

# Source env from DEV-FINAL .env.local for OPENROUTER_API_KEY (per task brief).
ENV_FILE="${ANTICIPY_ENV_FILE:-/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

TARGET="${TARGET:-100}"
MAX_RESTARTS="${MAX_RESTARTS:-10}"
COOL_DOWN_SEC="${COOL_DOWN_SEC:-60}"

mkdir -p state/v7 tasks
LOG="state/v7/stranger_batch_supervisor.log"
RUN_LOG="state/v7/stranger_batch_runs.log"
PID_FILE="tasks/stranger_batch_supervisor.pid"
STOP_FILE="tasks/stranger_batch_supervisor.stop"

rm -f "$STOP_FILE"
echo $$ > "$PID_FILE"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

log "supervisor starting pid=$$ target=$TARGET max_restarts=$MAX_RESTARTS"

current_count() {
  python3 scripts/v6/breadth_audit.py >/dev/null 2>&1 || true
  jq -r '.successful_interactions // 0' state/stranger_breadth.json 2>/dev/null || echo 0
}

last_stranger_uuid() {
  ls -1t state/strangers 2>/dev/null | head -1
}

last_run_failure_reason() {
  # Look for the most recently created stranger dir and pull the latest signal:
  # verdict.json -> reasons; else last line of run.log; else upload_response.json.
  local uuid dir verdict reason
  uuid="$(last_stranger_uuid)"
  if [ -z "$uuid" ]; then
    echo "no_strangers"
    return
  fi
  dir="state/strangers/$uuid"
  if [ -f "$dir/verdict.json" ]; then
    reason="$(jq -r '(.failures // .reasons // []) | join("; ")' "$dir/verdict.json" 2>/dev/null)"
    if [ -n "$reason" ] && [ "$reason" != "null" ]; then
      echo "$uuid: $reason"
      return
    fi
  fi
  if [ -f "$dir/run.log" ]; then
    reason="$(tail -3 "$dir/run.log" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g')"
    if [ -n "$reason" ]; then
      echo "$uuid: $reason"
      return
    fi
  fi
  echo "$uuid: no_signal"
}

existing_batch_pid() {
  pgrep -f "scripts/v7/run_until_100.sh" 2>/dev/null | head -1
}

restarts=0
while ! [ -f "$STOP_FILE" ]; do
  cnt="$(current_count)"
  if [ "$cnt" -ge "$TARGET" ] 2>/dev/null; then
    log "target reached: $cnt >= $TARGET; supervisor exiting clean"
    break
  fi

  if [ "$restarts" -ge "$MAX_RESTARTS" ]; then
    log "max restarts ($MAX_RESTARTS) reached at count=$cnt; supervisor stopping"
    break
  fi

  existing="$(existing_batch_pid)"
  if [ -n "$existing" ]; then
    # Another process owns the batch (master supervisor's loop_strangers or a
    # previous restart we spawned). Wait for it to exit, then decide.
    log "attached to existing batch pid=$existing count=$cnt; monitoring"
    while kill -0 "$existing" 2>/dev/null; do
      if [ -f "$STOP_FILE" ]; then
        break 2
      fi
      cnt2="$(current_count)"
      if [ "$cnt2" -ge "$TARGET" ] 2>/dev/null; then
        log "target reached during monitor: $cnt2 >= $TARGET"
        break 2
      fi
      sleep 30
    done
    last_uuid="$(last_stranger_uuid)"
    reason="$(last_run_failure_reason)"
    log "attached batch pid=$existing exited; last_uuid=$last_uuid reason=$reason"
    sleep "$COOL_DOWN_SEC"
    continue
  fi

  restarts=$((restarts + 1))
  log "starting batch run restart=$restarts/$MAX_RESTARTS count=$cnt"
  : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY missing; cannot run batch}"
  nohup bash scripts/v7/run_until_100.sh "$TARGET" >> "$RUN_LOG" 2>&1 &
  BATCH_PID=$!
  log "spawned batch pid=$BATCH_PID"
  wait "$BATCH_PID"
  EXIT=$?
  last_uuid="$(last_stranger_uuid)"
  reason="$(last_run_failure_reason)"
  log "batch pid=$BATCH_PID exited rc=$EXIT last_uuid=$last_uuid reason=$reason"
  sleep "$COOL_DOWN_SEC"
done

log "supervisor exiting (restarts=$restarts final_count=$(current_count))"
rm -f "$PID_FILE"
exit 0
