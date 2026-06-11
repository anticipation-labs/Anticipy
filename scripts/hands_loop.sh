#!/usr/bin/env bash
# THE HANDS DONE-TEST (section 8, headless portion).
# A goal runs end to end through the REAL hands: the API hand (MOCK) sends an
# email step; the no-Arcade-tool post_to_x reroutes to the browser hand over the
# real WS (simulated extension), returning a screenshot. Asserts verify-before-
# done, glass-box trail, scorecard, and smart-model-used-exactly-twice.
#
# The two LIVE proofs that need a one-time human action are NOT in here (a real
# Gmail send needs your OAuth approval; the real Chrome extension needs loading):
#   - engine/scripts/live_gmail_send.py   (after you approve the Gmail connect URL)
#   - load extension/ via chrome://extensions -> Load unpacked
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="$REPO/engine"
PY="$ENGINE_DIR/.venv/bin/python"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8794}"
export ANTICIPY_DATA_DIR="$(mktemp -d -t anticipy-hands-XXXXXX)"
export ANTICIPY_HANDS_MODE="${ANTICIPY_HANDS_MODE:-mock}"   # no real sends in this test
# This test's whole point is the reroute leg reaching the REAL browser hand over
# the real WS (simulated extension); the API hand stays mock. Without this the
# mock browser hand answers the reroute itself and the WS leg goes untested.
export ANTICIPY_BROWSER_HAND_MODE=live

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "port $PORT busy" >&2; exit 1; fi
"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT
curl -fsS --retry 40 --retry-delay 1 --retry-connrefused "http://$HOST:$PORT/health" >/dev/null
echo "engine up (hands mode: $ANTICIPY_HANDS_MODE)"

"$PY" "$ENGINE_DIR/scripts/_hands_loop_run.py" "http://$HOST:$PORT"
echo
echo "PASS: real hands integrated through the brain (API hand + browser hand on the frozen contract)."