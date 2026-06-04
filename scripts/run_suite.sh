#!/usr/bin/env bash
# Regression harness — runs the full existing suite. Used as the hard guard:
# after every browser-hand change, this must stay green.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/engine/.venv/bin/python"
export PYTHONPATH="$REPO/engine"
pass=0; fail=0; failed=""

run() {  # name, command...
  local name="$1"; shift
  if "$@" >/tmp/suite_"$name".log 2>&1; then
    echo "  PASS  $name"; pass=$((pass+1))
  else
    echo "  FAIL  $name   (see /tmp/suite_$name.log)"; fail=$((fail+1)); failed="$failed $name"
  fi
}

echo "== unit (free, deterministic) =="
for t in bus workers gateway orchestrator proactive glassbox_scorecard api_hand browser_hand handoff memory; do
  run "$t" "$PY" "$REPO/engine/scripts/test_$t.py"
done

echo "== integration (boot engine/extension; free/stub) =="
run brain_loop      bash "$REPO/scripts/brain_loop.sh"
run hands_loop      bash "$REPO/scripts/hands_loop.sh"
run extension_link  bash "$REPO/engine/scripts/test_extension_link.sh"
run browser_hand_io bash "$REPO/engine/scripts/test_browser_hand.sh"

echo
echo "==== SUITE: $pass passed, $fail failed ====${failed:+  FAILED:$failed}"
[ "$fail" -eq 0 ] && echo "SUITE GREEN" || echo "SUITE RED"
exit "$fail"
