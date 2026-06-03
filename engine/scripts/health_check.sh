#!/usr/bin/env bash
# Room 1 test: boot THIS engine and prove /health returns our signature.
# Hardened: binds a dedicated port (8000 is often taken by other local services),
# fails if uvicorn can't bind, and asserts the response is OUR engine — never a
# pass-through to some other server that happens to answer on the port.
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ENGINE_DIR/.venv/bin/python"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8787}"

# Refuse to run if the port is already taken — otherwise we'd test someone else.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port $PORT already in use; set ANTICIPY_ENGINE_PORT to a free port." >&2
  exit 1
fi

"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app \
  --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT

echo "--- GET http://$HOST:$PORT/health ---"
RESP="$(curl -fsS --retry 40 --retry-delay 1 --retry-connrefused \
  -w $'\nHTTP %{http_code}' "http://$HOST:$PORT/health")"
echo "$RESP"

# Assertions: it must be alive AND it must be OUR engine.
kill -0 "$SRV" 2>/dev/null || { echo "FAIL: engine process died (bind failure?)" >&2; exit 1; }
echo "$RESP" | grep -q '"service":"anticipy-engine"' || { echo "FAIL: not our engine signature" >&2; exit 1; }
echo "$RESP" | grep -q 'HTTP 200' || { echo "FAIL: non-200" >&2; exit 1; }

echo "--- PASS: anticipy-engine answered on $HOST:$PORT (local-first) ---"
