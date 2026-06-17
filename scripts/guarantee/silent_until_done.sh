#!/usr/bin/env bash
# Anticipy silent completion supervisor.
#
# Keeps the Mac awake, re-runs the DONE gate (and the 10k cert when stale), logs everything to
# docs/guarantee/logs/, recovers from crashes, and emits NOTHING to any chat surface. It stops only
# when assert_done.py is satisfiable (DONE_CERTIFIED or SOFTWARE_CERTIFIED_READY_FOR_OWNER_5DAY) or a
# sentinel file docs/guarantee/IMPOSSIBLE.txt is written by the agent (true physical blocker).
#
# This supervisor does the MECHANICAL, repeatable work (keep-awake, run cert, run gate, log). The
# intelligent build/fix work is done by the Claude completion foreman across its turns; this script
# is the durable heartbeat that the gate is being checked and the long runs are progressing.
#
# Usage:  bash scripts/guarantee/silent_until_done.sh            # supervise (foreground/background)
#         RUN_CERT=1 bash scripts/guarantee/silent_until_done.sh  # also (re)run the 10k cert each cycle
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1
LOGDIR="$ROOT/docs/guarantee/logs"
mkdir -p "$LOGDIR"
SUP_LOG="$LOGDIR/supervisor.log"
PY="$ROOT/engine/.venv/bin/python"
IMPOSSIBLE="$ROOT/docs/guarantee/IMPOSSIBLE.txt"
INTERVAL="${INTERVAL:-300}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >> "$SUP_LOG"; }

# Keep the machine awake for the duration (no-op if caffeinate absent).
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -dimsu -w $$ &
  log "caffeinate armed (pid $!)"
fi

# shellcheck disable=SC1091
set -a; source "$ROOT/.env.local" 2>/dev/null; set +a
export ANTICIPY_MODEL_PROVIDER="${ANTICIPY_MODEL_PROVIDER:-openrouter}"
export ANTICIPY_HANDS_MODE="${ANTICIPY_HANDS_MODE:-mock}"
export ANTICIPY_CHANNELS_MODE="${ANTICIPY_CHANNELS_MODE:-mock}"
export ANTICIPY_INBOUND_POLL_SECONDS="${ANTICIPY_INBOUND_POLL_SECONDS:-0}"
export PYTHONPATH="$ROOT/engine"

log "supervisor start (interval=${INTERVAL}s, RUN_CERT=${RUN_CERT:-0})"

cycle=0
while true; do
  cycle=$((cycle + 1))

  if [ -f "$IMPOSSIBLE" ]; then
    log "IMPOSSIBLE sentinel present — stopping supervisor for owner action"
    exit 2
  fi

  if [ "${RUN_CERT:-0}" = "1" ]; then
    log "cycle $cycle: running 10k cert"
    rm -rf "$ROOT/DONE_CERTIFICATION_BUNDLE"
    "$PY" "$ROOT/engine/scripts/cert_harness.py" --personas 100 --scenarios 100 \
        --concurrency 10 --out "$ROOT/DONE_CERTIFICATION_BUNDLE" \
        >> "$LOGDIR/cert_cycle_${cycle}.log" 2>&1 || log "cycle $cycle: cert exited nonzero"
  fi

  log "cycle $cycle: running DONE gate"
  if "$PY" "$ROOT/scripts/guarantee/assert_done.py" >> "$LOGDIR/assert_cycle_${cycle}.log" 2>&1; then
    log "cycle $cycle: DONE GATE SATISFIABLE — supervisor stopping (see assert_cycle_${cycle}.log)"
    exit 0
  fi
  log "cycle $cycle: not done; sleeping ${INTERVAL}s"
  sleep "$INTERVAL"
done
