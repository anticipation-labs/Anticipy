#!/usr/bin/env bash
# loops_status.sh - small status board for ralph_v7.
#
# Prints PID, last cycle index, gate counts, plus pointers to the
# completion / stuck files if either is present.
#
# Usage: bash tools/loops_status.sh

set -uo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

PIDFILE="state/v7/loop.pid"
CYCLE_FILE="state/v7/loop_cycle.txt"
LAST_CHECK="state/check_done_v7.json"
COMPLETE_FILE="state/v7/COMPLETE_ENGINEERING.md"
STUCK_FILE="state/v7/loop_stuck.md"
LOG_FILE="state/v7/loop.log"

echo "=== ralph_v7 status ==="
echo "time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || echo "")"
  if [ -n "$pid" ] && ps -p "$pid" >/dev/null 2>&1; then
    echo "loop: RUNNING (pid=$pid)"
  else
    echo "loop: NOT RUNNING (stale pidfile pid=$pid)"
  fi
else
  echo "loop: NOT RUNNING (no pidfile)"
fi

if [ -f "$CYCLE_FILE" ]; then
  echo "last cycle: $(cat "$CYCLE_FILE")"
else
  echo "last cycle: none"
fi

if [ -f "$LAST_CHECK" ]; then
  python3 - "$LAST_CHECK" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], "r"))
gates = data.get("gates") or {}
total = len(gates)
green = sum(1 for v in gates.values() if v is True)
red = sum(1 for v in gates.values() if v is False)
print(f"gates: total={total} green={green} red={red}")
red_list = [k for k, v in gates.items() if v is False]
if red_list:
    print("red:")
    for name in red_list:
        print(f"  - {name}")
else:
    print("red: none")
PY
else
  echo "gates: $LAST_CHECK not present yet"
fi

if [ -f "$COMPLETE_FILE" ]; then
  echo "COMPLETE_ENGINEERING: $COMPLETE_FILE"
fi
if [ -f "$STUCK_FILE" ]; then
  echo "LOOP_STUCK: $STUCK_FILE"
fi

if [ -f "$LOG_FILE" ]; then
  echo
  echo "--- last 10 log lines ($LOG_FILE) ---"
  tail -n 10 "$LOG_FILE"
fi
