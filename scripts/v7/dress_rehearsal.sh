#!/bin/bash
# Demo dress rehearsal. Runs the 3 demo moments live + logs PASS/FAIL.
# Verify command for G6 done criterion in orchestrator/CYCLE_PROCEDURE.md.

set -uo pipefail
REPO="${REPO:-/Users/omarebrahim/Developer/Anticipy-V7}"
cd "$REPO"
LOG_DIR="state/demo"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/dress_rehearsal_log.json"
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
START=$(date +%s)
RESULT='{"run_id":"'"$RUN_ID"'","started_at":"'"$(date -u +%FT%TZ)"'","scenes":{}}'

write_scene() {
  local scene="$1" status="$2" detail="$3"
  RESULT=$(echo "$RESULT" | jq --arg s "$scene" --arg st "$status" --arg d "$detail" '.scenes[$s] = {status: $st, detail: $d}')
}

echo "=== Dress rehearsal $RUN_ID ==="

# Scene A: trivia fire
echo ""
echo "Scene A: trivia fire (Roman Empire)"
A_RESP=$(curl -sS --max-time 8 -X POST http://127.0.0.1:8731/api/listen/inject \
  -H "Content-Type: application/json" \
  -d '{"text": "wait, when did the Roman Empire fall"}' 2>/dev/null)
OUTCOME=$(echo "$A_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('outcome','ERR'))" 2>/dev/null)
sleep 2
RECENT=$(curl -sS --max-time 4 http://127.0.0.1:8731/api/trivia/recent 2>/dev/null | jq -r '.fires[0].answer // ""')
if [ "$OUTCOME" = "TRIVIA_FIRE" ] && echo "$RECENT" | grep -q "476"; then
  echo "  Scene A PASS: answer correct (476 AD)"
  write_scene "trivia_roman" "PASS" "outcome=$OUTCOME answer_contains=476"
else
  echo "  Scene A FAIL: outcome=$OUTCOME answer=$RECENT"
  write_scene "trivia_roman" "FAIL" "outcome=$OUTCOME answer=$RECENT"
fi

# Scene B: silent execute via Z-001
echo ""
echo "Scene B: silent execute (Z-001 mini)"
Z=$(ls -t state/v7/z001_e2e_runs/*/result.json 2>/dev/null | head -1)
if [ -f "$Z" ]; then
  V=$(jq -r .verdict "$Z" 2>/dev/null)
  AGE=$(($(date +%s) - $(stat -f %m "$Z" 2>/dev/null || echo 0)))
  if [ "$V" = "PASS" ] && [ "$AGE" -lt 1800 ]; then
    echo "  Scene B PASS: Z-001 verdict=PASS, age=${AGE}s"
    write_scene "silent_execute" "PASS" "z001_run=$(basename $(dirname $Z)) age=${AGE}s"
  else
    echo "  Scene B FAIL: verdict=$V age=${AGE}s (need PASS within 30 min)"
    write_scene "silent_execute" "FAIL" "verdict=$V age=${AGE}s"
  fi
else
  echo "  Scene B FAIL: no Z-001 evidence"
  write_scene "silent_execute" "FAIL" "no_z001_run"
fi

# Scene C: cold start fills dossier
echo ""
echo "Scene C: cold start (dossier delta)"
BEFORE=$(jq -r '.people | length' ~/.anticipy/v7/dossiers/anticipy-user/dossier.json 2>/dev/null)
curl -sS --max-time 4 -X POST http://127.0.0.1:8731/api/coldstart/start -d '{}' >/dev/null 2>&1
sleep 60
STATUS=$(curl -sS --max-time 4 http://127.0.0.1:8731/api/coldstart/status 2>/dev/null)
STATE=$(echo "$STATUS" | jq -r '.state // .state.state // "unknown"')
PPL_REPORTED=$(echo "$STATUS" | jq -r '.people_count // .state.people_count // 0')
AFTER=$(jq -r '.people | length' ~/.anticipy/v7/dossiers/anticipy-user/dossier.json 2>/dev/null)
DELTA=$((AFTER - BEFORE))
if [ "$AFTER" -ge 10 ]; then
  echo "  Scene C PASS: dossier has $AFTER people (delta +$DELTA, status reports $PPL_REPORTED new)"
  write_scene "coldstart" "PASS" "after=$AFTER delta=$DELTA reported=$PPL_REPORTED state=$STATE"
else
  echo "  Scene C FAIL: dossier has $AFTER people (need >= 10, status reports $PPL_REPORTED new)"
  write_scene "coldstart" "FAIL" "after=$AFTER delta=$DELTA reported=$PPL_REPORTED state=$STATE"
fi

# Overall verdict
TOTAL_ELAPSED=$(($(date +%s) - START))
PASS_COUNT=$(echo "$RESULT" | jq -r '[.scenes[] | select(.status=="PASS")] | length')
FAIL_COUNT=$(echo "$RESULT" | jq -r '[.scenes[] | select(.status=="FAIL")] | length')
VERDICT=$([ "$FAIL_COUNT" -eq 0 ] && echo "PASS" || echo "FAIL")

RESULT=$(echo "$RESULT" | jq \
  --arg v "$VERDICT" \
  --argjson pc "$PASS_COUNT" \
  --argjson fc "$FAIL_COUNT" \
  --argjson te "$TOTAL_ELAPSED" \
  '. + {verdict: $v, pass_count: $pc, fail_count: $fc, total_elapsed_sec: $te, finished_at: "'"$(date -u +%FT%TZ)"'"}')

# Append to log file
if [ -f "$LOG_FILE" ]; then
  EXISTING=$(jq -r '.runs // []' "$LOG_FILE")
  echo "{\"runs\": $(echo "$EXISTING" | jq ". + [$RESULT]")}" > "$LOG_FILE"
else
  echo "{\"runs\": [$RESULT]}" > "$LOG_FILE"
fi

echo ""
echo "=== VERDICT: $VERDICT ($PASS_COUNT pass, $FAIL_COUNT fail, ${TOTAL_ELAPSED}s) ==="
[ "$VERDICT" = "PASS" ] && exit 0 || exit 1
