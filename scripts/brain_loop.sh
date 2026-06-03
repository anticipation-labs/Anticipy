#!/usr/bin/env bash
# THE DONE-TEST for the control core (section 6).
# One stub-driven end-to-end run, in TWO real processes that share a data dir so
# the restart/resume hop (6) is a genuine process restart:
#   part 1: event -> gate -> plan -> dispatch (connector fails once -> retry) ->
#           verify-before-done -> done; asserts smart x2, glass-box, scorecard.
#   part 2 (fresh process): reload the waiting goal from disk and resume to done.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/engine/.venv/bin/python"
export PYTHONPATH="$REPO/engine"
export ANTICIPY_DATA_DIR="$(mktemp -d -t anticipy-brainloop-XXXXXX)"
echo "data dir: $ANTICIPY_DATA_DIR"

echo
echo "== PART 1: feed -> gate -> plan -> dispatch (retry once) -> verify -> done =="
OUT1="$("$PY" "$REPO/engine/scripts/brain_loop_part1.py")"
echo "$OUT1"
echo "$OUT1" | grep -q "PART1 PASS" || { echo "FAIL: part 1" >&2; exit 1; }

echo
echo "== PART 2 (fresh process = engine restart): resume the waiting goal from disk =="
OUT2="$("$PY" "$REPO/engine/scripts/brain_loop_part2.py")"
echo "$OUT2"
echo "$OUT2" | grep -q "PART2 PASS" || { echo "FAIL: part 2" >&2; exit 1; }

echo
echo "PASS: control core proven end to end — decide -> plan -> dispatch -> retry -> verify -> done; survives restart; smart used exactly twice; glass-box + scorecard intact."
