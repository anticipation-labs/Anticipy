#!/usr/bin/env bash
# Piece 6 (HTTP): the control core over HTTP — feed an event, read the glass-box
# feed and the scorecard.
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ENGINE_DIR/.venv/bin/python"
HOST=127.0.0.1
PORT="${ANTICIPY_ENGINE_PORT:-8791}"
export ANTICIPY_DATA_DIR="$(mktemp -d -t anticipy-corehttp-XXXXXX)"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "port $PORT busy" >&2; exit 1; fi
"$PY" -m uvicorn --app-dir "$ENGINE_DIR" anticipy_engine.main:app --host "$HOST" --port "$PORT" --log-level warning &
SRV=$!
trap 'kill "$SRV" 2>/dev/null || true' EXIT
BASE="http://$HOST:$PORT"
curl -fsS --retry 40 --retry-delay 1 --retry-connrefused "$BASE/health" >/dev/null

echo "--- POST /event ---"
curl -fsS -X POST "$BASE/event" -H 'content-type: application/json' \
  -d '{"text":"I'\''ll send Sarah the Q3 deck on Friday and book us lunch.","source":"app"}'; echo

echo "--- GET /glassbox ---"
GB="$(curl -fsS "$BASE/glassbox?limit=50")"
echo "$GB"
echo "$GB" | grep -q '"kind":"goal_done"' || { echo "FAIL: no goal_done in glass-box" >&2; exit 1; }
echo "$GB" | grep -q '"kind":"decision"' || { echo "FAIL: no decision in glass-box" >&2; exit 1; }

echo "--- GET /scorecard ---"
SC="$(curl -fsS "$BASE/scorecard")"
echo "$SC"
echo "$SC" | grep -q '"success":1' || { echo "FAIL: scorecard missing success goal" >&2; exit 1; }

echo "--- PASS: control core HTTP (event -> glass-box + scorecard) ---"
