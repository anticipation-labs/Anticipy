#!/usr/bin/env bash
# Room 4 test: boot the engine, then run the extension's real connect logic
# (engine_client.js) against it via Node and assert "connected".
set -euo pipefail

EXT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="$(cd "$EXT_DIR/../engine" && pwd)"
PY="$ENGINE_DIR/.venv/bin/python"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8789}"
export ANTICIPY_DATA_DIR="$(mktemp -d -t anticipy-ext-XXXXXX)"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port $PORT busy; set ANTICIPY_ENGINE_PORT." >&2; exit 1
fi

"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app \
  --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT

curl -fsS --retry 40 --retry-delay 1 --retry-connrefused "http://$HOST:$PORT/health" >/dev/null

node "$EXT_DIR/test/connect_test.js" "http://$HOST:$PORT"
