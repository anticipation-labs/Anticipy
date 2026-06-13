#!/usr/bin/env bash
# Engine HTTP compatibility wiring: capture -> ControlCore feed -> memory write ->
# read back, plus the extension-connected handshake. Isolated temp data dir; dedicated port.
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ENGINE_DIR/.venv/bin/python"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8788}"
DATA_DIR="$(mktemp -d -t anticipy-brain-XXXXXX)"
export ANTICIPY_DATA_DIR="$DATA_DIR"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port $PORT busy; set ANTICIPY_ENGINE_PORT." >&2; exit 1
fi

"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app \
  --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT

BASE="http://$HOST:$PORT"
curl -fsS --retry 40 --retry-delay 1 --retry-connrefused "$BASE/health" >/dev/null

echo "--- POST /capture {text: hello from the mic} ---"
CAP="$(curl -fsS -X POST "$BASE/capture" -H 'content-type: application/json' -d '{"text":"hello from the mic"}')"
echo "$CAP"
echo "$CAP" | grep -Eq '"decision"|"category"' || { echo "FAIL: ControlCore did not answer capture" >&2; exit 1; }

echo "--- GET /memory/history (another client reads the scrap back) ---"
HIST="$(curl -fsS "$BASE/memory/history")"
echo "$HIST"
echo "$HIST" | grep -q 'hello from the mic' || { echo "FAIL: scrap not in history" >&2; exit 1; }

echo "--- POST /extension/hello ---"
curl -fsS -X POST "$BASE/extension/hello" -H 'content-type: application/json' -d '{"client":"chrome"}'; echo

echo "--- GET /status ---"
ST="$(curl -fsS "$BASE/status")"; echo "$ST"
echo "$ST" | grep -q '"extension_connected":true' || { echo "FAIL: extension not connected" >&2; exit 1; }

echo "--- PASS: engine HTTP compatibility wiring (capture -> real core -> memory -> read back; extension connected) ---"
