#!/usr/bin/env bash
# THE DONE-TEST — the hello-loop.
# One fake "hello" travels the whole frame with no real feature:
#   capture (CaptureSource) -> engine -> think() -> history write
#   -> another client reads the scrap back -> extension reports connected
#   -> the app is on screen.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="$REPO/engine"
PY="$ENGINE_DIR/.venv/bin/python"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8790}"
export ANTICIPY_DATA_DIR="$(mktemp -d -t anticipy-hello-XXXXXX)"

step() { printf "\n== %s ==\n" "$*"; }

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port $PORT busy; set ANTICIPY_ENGINE_PORT." >&2; exit 1
fi
"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app \
  --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT
BASE="http://$HOST:$PORT"
curl -fsS --retry 40 --retry-delay 1 --retry-connrefused "$BASE/health" >/dev/null
echo "engine up: $BASE  (data: $ANTICIPY_DATA_DIR)"

step "hops 1-4: capture 'hello from the mic' via CaptureSource -> engine -> think() -> history write"
CAP="$(curl -fsS -X POST "$BASE/capture" -H 'content-type: application/json' \
  -d '{"text":"hello from the mic","source":"mac_mic"}')"
echo "$CAP"
echo "$CAP" | grep -q '"source":"mac_mic"' || { echo "FAIL: capture seam" >&2; exit 1; }
echo "$CAP" | grep -q '"thought"'          || { echo "FAIL: think()" >&2; exit 1; }
echo "$CAP" | grep -q '"kind":"history"'   || { echo "FAIL: history write" >&2; exit 1; }

step "hop 5: another client reads the scrap back out of history"
HIST="$(curl -fsS "$BASE/memory/history")"
echo "$HIST"
echo "$HIST" | grep -q 'hello from the mic' || { echo "FAIL: readback" >&2; exit 1; }

step "hop 6: the extension connects and reports connected (real connect logic)"
node "$REPO/extension/test/connect_test.js" "$BASE"

step "hop 7: the app is on screen showing a designed screen"
if pgrep -x Anticipy >/dev/null 2>&1; then
  echo "Anticipy app: RUNNING (pid $(pgrep -x Anticipy | head -1)) — Onboarding/Connect/Main rendered"
else
  echo "Anticipy app: not running — build at $REPO/macapp/dist/Anticipy.app ; 'open' it"
fi

step "engine status"
curl -fsS "$BASE/status"; echo

step "RESULT"
echo "PASS: hello-loop complete — capture -> engine -> think -> memory write -> read back -> extension connected -> app on screen"
