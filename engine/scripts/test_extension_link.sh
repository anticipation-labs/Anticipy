#!/usr/bin/env bash
# Piece 2 test: boot the engine and exercise the authenticated extension WS link
# (reject unauth, ping/pong keepalive, reload broadcast) with a simulated client.
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ENGINE_DIR/.venv/bin/python"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8792}"
export ANTICIPY_DATA_DIR="$(mktemp -d -t anticipy-wslink-XXXXXX)"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "port $PORT busy" >&2; exit 1; fi
"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT
curl -fsS --retry 40 --retry-delay 1 --retry-connrefused "http://$HOST:$PORT/health" >/dev/null

"$PY" "$ENGINE_DIR/scripts/_extension_link_client.py" "http://$HOST:$PORT"