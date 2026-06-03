#!/usr/bin/env bash
# Piece 3 test: unit edge-cases + a real-WS integration (simulated extension
# drives the real BrowserHand through the engine).
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ENGINE_DIR/.venv/bin/python"
export PYTHONPATH="$ENGINE_DIR"

echo "--- unit (FakeLink) ---"
"$PY" "$ENGINE_DIR/scripts/test_browser_hand.py"

echo "--- integration (real WS + simulated extension) ---"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8793}"
export ANTICIPY_DATA_DIR="$(mktemp -d -t anticipy-bh-XXXXXX)"
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "port $PORT busy" >&2; exit 1; fi
"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT
curl -fsS --retry 40 --retry-delay 1 --retry-connrefused "http://$HOST:$PORT/health" >/dev/null
"$PY" "$ENGINE_DIR/scripts/_browser_hand_integration.py" "http://$HOST:$PORT"