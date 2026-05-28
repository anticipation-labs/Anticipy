#!/usr/bin/env bash
# Profile the LIVE engine on port 8731 under representative load.
# READ-ONLY HTTP. Does not restart engine. Safe to run while the
# strangers loop is running.
#
# Usage: bash scripts/v7/engine_load_profile.sh
set -u

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENGINE_URL="${ANTICIPY_ENGINE_URL:-http://127.0.0.1:8731}"
ACCOUNT="${ANTICIPY_ACCOUNT_ID:-e2e_rich_test_2026_05_28}"
TRANSCRIPTS="$REPO/state/v7/hard_proactive_transcripts.json"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$REPO/state/v7/engine_load_profile_${TS}"
SAMPLE_SECONDS="${SAMPLE_SECONDS:-30}"
INTENT_CALL_BUDGET="${INTENT_CALL_BUDGET:-10}"
ENGINE_LOG="$HOME/.anticipy/product-engine.log"

mkdir -p "$RUN_DIR"

echo "=== Anticipy V7 engine load profile ==="
echo "engine: $ENGINE_URL"
echo "account: $ACCOUNT"
echo "run dir: $RUN_DIR"
echo

# Find the engine PID listening on 8731.
PID="$(lsof -nP -iTCP:8731 -sTCP:LISTEN -t 2>/dev/null | head -1)"
if [ -z "$PID" ]; then
  echo "engine PID not found on 8731; profile will skip sample step"
fi
echo "engine pid: ${PID:-unknown}"

# Confirm /version up.
ver="$(curl -fsS --max-time 5 "$ENGINE_URL/version" || echo 'unreachable')"
echo "engine version: $ver"
echo "$ver" > "$RUN_DIR/version.json"

# Pre-flight: capture log tail offset.
log_offset=0
if [ -f "$ENGINE_LOG" ]; then
  log_offset="$(wc -c < "$ENGINE_LOG" | tr -d ' ')"
fi
echo "log offset: $log_offset bytes"

# Snapshot openapi paths so analysis knows what was actually mounted.
curl -fsS --max-time 5 "$ENGINE_URL/openapi.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(sorted(d['paths'].keys()),indent=2))" \
  > "$RUN_DIR/mounted_paths.json" 2>/dev/null || echo '[]' > "$RUN_DIR/mounted_paths.json"

# Kick off sample(1) on the engine PID in background (30s default).
SAMPLE_FILE="$RUN_DIR/sample.txt"
if [ -n "${PID:-}" ]; then
  echo "starting sample $PID ${SAMPLE_SECONDS}s in background..."
  ( sample "$PID" "$SAMPLE_SECONDS" -file "$SAMPLE_FILE" -mayDie >/dev/null 2>&1 ) &
  SAMPLE_PID=$!
  echo "sample pid: $SAMPLE_PID"
  # Give sample 1 second to attach before we slam the engine.
  sleep 1
fi

# Drive the load (pure-python, no extra deps).
echo
echo "=== driving load ==="
python3 "$REPO/scripts/v7/engine_load_profile_analyze.py" \
  --engine "$ENGINE_URL" \
  --account "$ACCOUNT" \
  --transcripts "$TRANSCRIPTS" \
  --run-dir "$RUN_DIR" \
  --intent-budget "$INTENT_CALL_BUDGET" \
  --inject-n 100 --inject-conc 32 \
  --dossier-n 100 --dossier-conc 32 \
  --status-n 100 --status-conc 32 \
  --intent-conc 5

# Wait for sample to finish if we launched it.
if [ -n "${SAMPLE_PID:-}" ]; then
  echo "waiting for sample to finish..."
  wait "$SAMPLE_PID" 2>/dev/null || true
  if [ -f "$SAMPLE_FILE" ]; then
    sz="$(wc -c < "$SAMPLE_FILE" | tr -d ' ')"
    echo "sample written: $SAMPLE_FILE (${sz} bytes)"
  fi
fi

# Tail the engine log since pre-flight offset and scan for 4xx/5xx/errors.
if [ -f "$ENGINE_LOG" ]; then
  python3 - <<PY > "$RUN_DIR/engine_log_tail.txt"
import sys
p = "$ENGINE_LOG"
off = int("$log_offset")
with open(p, "rb") as f:
    f.seek(off)
    data = f.read().decode("utf-8", errors="replace")
sys.stdout.write(data)
PY
  echo "engine log tail bytes: $(wc -c < "$RUN_DIR/engine_log_tail.txt" | tr -d ' ')"
  grep -E ' (429|500|502|503|504) | ERROR | WARNING |Traceback' "$RUN_DIR/engine_log_tail.txt" \
    > "$RUN_DIR/engine_log_errors.txt" 2>/dev/null || true
  err_lines="$(wc -l < "$RUN_DIR/engine_log_errors.txt" | tr -d ' ')"
  echo "engine log error/warning lines during load: $err_lines"
fi

# Final smoke: engine still up?
post_status="$(curl -fsS --max-time 5 -o /dev/null -w '%{http_code}' "$ENGINE_URL/version" 2>/dev/null || echo 000)"
echo "post-load /version status: $post_status"
echo "$post_status" > "$RUN_DIR/post_load_status.txt"

echo
echo "=== outputs ==="
ls -la "$RUN_DIR"
echo
echo "metrics: $RUN_DIR/metrics.json"
echo "analysis: $RUN_DIR/analysis.md"
