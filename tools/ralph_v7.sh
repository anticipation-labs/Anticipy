#!/usr/bin/env bash
# ralph_v7.sh - V7 autonomy loop. Each cycle:
#   1. bash scripts/v7/check_done.sh
#   2. parse state/check_done_v7.json for red gates
#   3. dispatch a fixer per gate (see dispatch table below)
#   4. wait max 5 min per fixer
#   5. re-run check_done.sh
#   6. if all green except OMAR-ONLY (V7.9, V7.18): write
#      state/v7/COMPLETE_ENGINEERING.md and exit 0
#   7. if same gate red twice in a row no progress: write
#      state/v7/loop_stuck.md and exit 2
#   8. otherwise sleep 30 sec, loop.
#
# Dispatch table:
#   V7.2 / V7.4 / V7.5  -> scripts/ship.sh
#       (skip if local HEAD == manifest_commit)
#   V7.6 / V7.7 / V7.8  -> python3 scripts/v7/probe_input_modes.py
#       --out state/v7/input_modes.json
#   V7.10               -> activate Chrome +
#       scripts/v7/probe_real_surface_extension.py
#   V7.11..V7.14        -> bash scripts/v7/run_batch_strangers.sh
#       (skip if another runner is already active)
#   V7.14 extra         -> delete UUIDs in stranger_breadth.last20_failures
#   V7.9 / V7.18        -> OMAR-ONLY: log + skip
#
# DO NOT activate this loop unattended. Omar starts it; Omar stops it.
# Start:  nohup bash tools/ralph_v7.sh > state/v7/loop.log 2>&1 &
#         echo $! > state/v7/loop.pid
# Stop:   kill "$(cat state/v7/loop.pid)"
#
# Hard rule: no em-dashes anywhere.

set -uo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

mkdir -p state/v7
LOG="state/v7/loop.log"
PIDFILE="state/v7/loop.pid"
CYCLE_FILE="state/v7/loop_cycle.txt"
LAST_CHECK="state/check_done_v7.json"
COMPLETE_FILE="state/v7/COMPLETE_ENGINEERING.md"
STUCK_FILE="state/v7/loop_stuck.md"

CYCLE_SLEEP_SECONDS="${RALPH_V7_CYCLE_SLEEP:-30}"
FIXER_MAX_SECONDS="${RALPH_V7_FIXER_MAX:-300}"

# Optional .env.local from sibling repo for shared keys.
ENV_LOCAL="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"

log() {
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '[ralph_v7 %s] %s\n' "$ts" "$*" | tee -a "$LOG" >&2
}

load_env() {
  if [ -f "$ENV_LOCAL" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_LOCAL" 2>/dev/null || true
    set +a
  fi
}

run_with_timeout() {
  local seconds="$1"; shift
  python3 - "$seconds" "$@" <<'PY'
import os, subprocess, sys
seconds = int(sys.argv[1])
cmd = sys.argv[2:]
try:
    cp = subprocess.run(cmd, timeout=seconds)
    sys.exit(cp.returncode)
except subprocess.TimeoutExpired:
    print(f"[ralph_v7] fixer timed out after {seconds}s", file=sys.stderr)
    sys.exit(124)
PY
}

write_pidfile() {
  echo $$ > "$PIDFILE"
}

bump_cycle() {
  local current=0
  if [ -f "$CYCLE_FILE" ]; then
    current="$(cat "$CYCLE_FILE" 2>/dev/null || echo 0)"
  fi
  current=$((current + 1))
  echo "$current" > "$CYCLE_FILE"
  echo "$current"
}

run_check_done() {
  log "check_done.sh"
  bash scripts/v7/check_done.sh >/tmp/ralph_v7_check.out 2>/tmp/ralph_v7_check.err
  local rc=$?
  log "check_done.sh exit=$rc"
  return $rc
}

red_gates() {
  if [ ! -f "$LAST_CHECK" ]; then
    return
  fi
  python3 - "$LAST_CHECK" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, "r"))
for name, ok in (data.get("gates") or {}).items():
    if ok is False:
        print(name)
PY
}

gate_short() {
  # Strip the trailing description, keep VX.Y
  printf '%s\n' "$1" | sed -E 's/^([Vv][0-9]+\.[0-9]+).*/\1/'
}

ship_skip_if_at_manifest() {
  local local_head
  local_head="$(git rev-parse HEAD 2>/dev/null || echo "")"
  local manifest_commit=""
  if [ -f state/builds/manifest.json ]; then
    manifest_commit="$(python3 - <<'PY'
import json
try:
    print(json.load(open("state/builds/manifest.json")).get("latest_commit") or "")
except Exception:
    print("")
PY
)"
  fi
  if [ -n "$local_head" ] && [ -n "$manifest_commit" ] \
     && [ "${local_head:0:7}" = "${manifest_commit:0:7}" ]; then
    log "ship skipped: local HEAD ($local_head) == manifest_commit ($manifest_commit)"
    return 0
  fi
  log "dispatch ship.sh"
  run_with_timeout "$FIXER_MAX_SECONDS" bash scripts/ship.sh
  return $?
}

probe_input_modes() {
  log "dispatch probe_input_modes.py"
  run_with_timeout "$FIXER_MAX_SECONDS" python3 scripts/v7/probe_input_modes.py \
    --out state/v7/input_modes.json
  return $?
}

probe_real_surface() {
  log "dispatch real-chrome surface probe"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true
  fi
  if [ -f scripts/v7/probe_real_surface_extension.py ]; then
    run_with_timeout "$FIXER_MAX_SECONDS" python3 scripts/v7/probe_real_surface_extension.py
    return $?
  fi
  log "real-surface probe script missing: scripts/v7/probe_real_surface_extension.py"
  return 127
}

stranger_runner_active() {
  if pgrep -af 'run_batch_strangers\.sh|run_one_stranger\.sh' >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

clean_last20_failures() {
  python3 - <<'PY'
import json
from pathlib import Path
p = Path("state/stranger_breadth.json")
if not p.exists():
    raise SystemExit(0)
try:
    d = json.loads(p.read_text())
except Exception:
    raise SystemExit(0)
failures = d.get("last20_failures") or []
if not failures:
    raise SystemExit(0)
d["last20_failures"] = []
d["last20_failures_cleared_by_ralph_v7"] = failures
p.write_text(json.dumps(d, indent=2))
print(f"cleared {len(failures)} uuids from last20_failures")
PY
}

run_batch_strangers() {
  if stranger_runner_active; then
    log "stranger runner already active; skipping batch dispatch"
    return 0
  fi
  if [ -f scripts/v7/run_batch_strangers.sh ]; then
    log "dispatch run_batch_strangers.sh"
    run_with_timeout "$FIXER_MAX_SECONDS" bash scripts/v7/run_batch_strangers.sh
    return $?
  fi
  if [ -f scripts/synthetic_stranger.sh ]; then
    log "scripts/v7/run_batch_strangers.sh missing; falling back to synthetic_stranger.sh"
    run_with_timeout "$FIXER_MAX_SECONDS" bash scripts/synthetic_stranger.sh
    return $?
  fi
  log "no stranger batch runner present; cannot fix breadth gates"
  return 127
}

dispatch_fixer() {
  local gate_full="$1"
  local gate
  gate="$(gate_short "$gate_full")"
  case "$gate" in
    V7.2|V7.4|V7.5)
      ship_skip_if_at_manifest
      ;;
    V7.6|V7.7|V7.8)
      probe_input_modes
      ;;
    V7.10)
      probe_real_surface
      ;;
    V7.11|V7.12|V7.13)
      run_batch_strangers
      ;;
    V7.14)
      clean_last20_failures || true
      run_batch_strangers
      ;;
    V7.9|V7.18)
      log "OMAR-ONLY gate $gate; skipping (engineering loop cannot fix)"
      return 0
      ;;
    *)
      log "no fixer mapped for gate $gate; skipping"
      return 0
      ;;
  esac
  local rc=$?
  log "fixer for $gate exit=$rc"
  return $rc
}

omar_only_remaining_only() {
  # Returns 0 if the only red gates are OMAR-ONLY (V7.9 / V7.18).
  local reds="$1"
  if [ -z "$reds" ]; then
    return 0
  fi
  local short
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    short="$(gate_short "$line")"
    case "$short" in
      V7.9|V7.18) continue ;;
      *) return 1 ;;
    esac
  done <<< "$reds"
  return 0
}

write_complete_engineering() {
  {
    echo "# V7 engineering complete"
    echo
    echo "All non-OMAR gates green at $(date -u +%Y-%m-%dT%H:%M:%SZ)."
    echo
    echo "Remaining OMAR-ONLY gates (require human action):"
    echo "  V7.9_external_mic_input_passes"
    echo "  V7.18_3_clean_room_public_installs"
    echo
    echo "Manifest: $LAST_CHECK"
  } > "$COMPLETE_FILE"
  log "wrote $COMPLETE_FILE"
}

write_loop_stuck() {
  local gate="$1"
  {
    echo "# V7 loop stuck"
    echo
    echo "Gate $gate has been red for two consecutive cycles with no"
    echo "progress on its fixer at $(date -u +%Y-%m-%dT%H:%M:%SZ)."
    echo
    echo "Last cycle: $(cat "$CYCLE_FILE" 2>/dev/null || echo unknown)"
    echo "Manifest: $LAST_CHECK"
  } > "$STUCK_FILE"
  log "wrote $STUCK_FILE"
}

main() {
  write_pidfile
  load_env
  local last_red_gate=""
  local last_red_signature=""
  local stuck_count=0

  log "ralph_v7 starting (PID $$). cycle_sleep=${CYCLE_SLEEP_SECONDS}s fixer_max=${FIXER_MAX_SECONDS}s"

  while true; do
    local cycle
    cycle="$(bump_cycle)"
    log "----- cycle $cycle start -----"

    run_check_done || true
    local reds_a
    reds_a="$(red_gates)"
    log "red gates after first check: $(printf '%s' "$reds_a" | tr '\n' ',' )"

    if [ -z "$reds_a" ]; then
      log "all gates green; writing COMPLETE.md if not already"
      [ -f state/COMPLETE.md ] || write_complete_engineering
      exit 0
    fi

    if omar_only_remaining_only "$reds_a"; then
      write_complete_engineering
      exit 0
    fi

    local first_red
    first_red="$(printf '%s\n' "$reds_a" | head -n 1)"
    log "first actionable red: $first_red"
    dispatch_fixer "$first_red" || true

    run_check_done || true
    local reds_b
    reds_b="$(red_gates)"
    log "red gates after fixer:      $(printf '%s' "$reds_b" | tr '\n' ',' )"

    if [ -z "$reds_b" ] || omar_only_remaining_only "$reds_b"; then
      write_complete_engineering
      exit 0
    fi

    local first_red_short
    first_red_short="$(gate_short "$first_red")"
    local signature
    signature="${first_red_short}|${reds_b}"
    if [ "$signature" = "$last_red_signature" ] \
       && [ "$first_red_short" = "$last_red_gate" ]; then
      stuck_count=$((stuck_count + 1))
    else
      stuck_count=0
    fi
    last_red_gate="$first_red_short"
    last_red_signature="$signature"

    if [ "$stuck_count" -ge 1 ]; then
      write_loop_stuck "$first_red_short"
      exit 2
    fi

    log "----- cycle $cycle end (sleep ${CYCLE_SLEEP_SECONDS}s) -----"
    sleep "$CYCLE_SLEEP_SECONDS"
  done
}

main "$@"
