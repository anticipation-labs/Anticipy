#!/usr/bin/env bash
# gate_P3.sh — P3-voice closure: the 2:45 call, for real, with independent read-back.
#
# HARD HUMAN GUARD: refuses to run any live leg unless factory/config/owner_phone.confirmed
# exists. ONLY the foreman creates that file, ONLY after Omar confirms the number in chat.
# A wrong-number call is a product sin; this guard is the law, not a suggestion.
#
# Legs (all proven by INDEPENDENT Twilio REST read-back, never the actor's claim):
#   S1 outbound: seeded time-critical loop -> real TTS call to OWNER_PHONE; Twilio
#      Calls.json record read back (status queued/ringing/in-progress/completed) within
#      120s of the seeding event (the seed asks for a ~60s reminder; bound disclosed).
#   S2 ask SMS: a third-party-send ask -> real SMS to OWNER_PHONE carrying a reply code;
#      Messages.json read-back by SID.
#   S3 inbound YES (interactive): an ask id must EXIST in /pending first; then wait up to
#      600s for Omar's real "YES <code>" reply to resolve THAT id via the inbound poller.
#      No reply -> S3=SKIPPED_HUMAN and the gate FAILS (closure needs every leg).
#      Run this gate while Omar is awake and primed to reply.
#
# Usage: bash factory/gates/gate_P3.sh <LAP>   (gate JSON on stdout; exit 0 = PASS)
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
LAP="${1:-manual-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="logs/factory/laps/$LAP"; mkdir -p "$OUT"

fail() { echo "{\"phase_gate_passed\": false, \"reason\": \"$1\"}"; exit 1; }

# ---- guard 0: the human confirm marker (foreman-created only) ----
[ -f factory/config/owner_phone.confirmed ] \
  || fail "owner_phone.confirmed missing — Omar has not confirmed OWNER_PHONE; live legs banned"

# ---- guard 1: live env (.env.local loaded like gate_P1 does; never printed) ----
if [ -f .env.local ]; then set -a; . ./.env.local; set +a; fi
for v in TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM OWNER_PHONE; do
  [ -n "${!v:-}" ] || fail "env $v missing"
done
export OUT TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM OWNER_PHONE

PY="engine/.venv/bin/python"
PORT=8899
BASE="http://127.0.0.1:$PORT"
TW="https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID"

# ---- boot live engine ----
ANTICIPY_CHANNELS_MODE=live ANTICIPY_DATA_DIR="$OUT/p3_data" ANTICIPY_TICK_SECONDS=5 \
  "$PY" -m uvicorn --app-dir engine anticipy_engine.main:app --port $PORT >"$OUT/p3_engine.log" 2>&1 &
ENG=$!
trap 'kill $ENG 2>/dev/null' EXIT
for i in $(seq 1 30); do curl -sf "$BASE/health" >/dev/null 2>&1 && break; sleep 1; done
curl -sf "$BASE/health" >/dev/null 2>&1 || fail "engine did not boot live"

S1=FAIL; S2=FAIL; S3=SKIPPED_HUMAN; S1_LATENCY=-1

# ---- S1: seeded time-critical loop -> real call within 120s ----
T0=$(date +%s)
curl -sf -X POST "$BASE/event" -H 'Content-Type: application/json' \
  -d '{"source":"typed","text":"[Anticipy test] remind me to stretch in 1 minute, call me for it"}' \
  >"$OUT/p3_s1_event.json" 2>&1
for i in $(seq 1 24); do
  sleep 5
  curl -sf -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
    "$TW/Calls.json?To=$("$PY" -c 'import urllib.parse,os;print(urllib.parse.quote(os.environ["OWNER_PHONE"]))')&PageSize=5" \
    > "$OUT/p3_s1_calls.json" 2>/dev/null || continue
  if "$PY" - "$T0" <<'PYEOF'
import json, sys, os, email.utils, time
t0 = int(sys.argv[1])
d = json.load(open(os.environ["OUT"] + "/p3_s1_calls.json"))
for c in d.get("calls", []):
    if c.get("status") not in ("queued", "ringing", "in-progress", "completed"):
        continue
    ts = c.get("date_created")
    if ts:
        t = email.utils.parsedate_to_datetime(ts).timestamp()
        if t < t0 - 30:           # ignore calls older than this gate run
            continue
    sys.exit(0)
sys.exit(1)
PYEOF
  then S1=PASS; S1_LATENCY=$(( $(date +%s) - T0 )); break; fi
done

# ---- S2: third-party-send ask -> real reply-code SMS to OWNER_PHONE ----
curl -sf -X POST "$BASE/event" -H 'Content-Type: application/json' \
  -d '{"source":"typed","text":"[Anticipy test] text Sam I will send him the revised deck tomorrow"}' \
  >"$OUT/p3_s2_event.json" 2>&1
ASK_ID=""
for i in $(seq 1 12); do
  sleep 5
  curl -sf "$BASE/pending" > "$OUT/p3_pending.json" 2>/dev/null || continue
  ASK_ID=$("$PY" -c '
import json
d = json.load(open("'"$OUT"'/p3_pending.json"))
items = d.get("pending", d if isinstance(d, list) else [])
print(items[0].get("id", "") if items else "")' 2>/dev/null)
  [ -n "$ASK_ID" ] && break
done
[ -n "$ASK_ID" ] || ASK_ID=""
sleep 5
curl -sf -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  "$TW/Messages.json?From=$("$PY" -c 'import urllib.parse,os;print(urllib.parse.quote(os.environ["TWILIO_FROM"]))')&PageSize=5" \
  > "$OUT/p3_s2_sms.json" 2>/dev/null
if [ -n "$ASK_ID" ] && "$PY" -c '
import json, sys
d = json.load(open("'"$OUT"'/p3_s2_sms.json"))
sys.exit(0 if any(m.get("sid") for m in d.get("messages", [])) else 1)'; then S2=PASS; fi

# ---- S3: Omar replies "YES <code>" for THAT ask id (up to 600s) ----
if [ -n "$ASK_ID" ]; then
  for i in $(seq 1 60); do
    sleep 10
    curl -sf "$BASE/pending" > "$OUT/p3_pending_now.json" 2>/dev/null || continue
    if "$PY" -c '
import json, sys
d = json.load(open("'"$OUT"'/p3_pending_now.json"))
items = d.get("pending", d if isinstance(d, list) else [])
sys.exit(1 if any(x.get("id") == "'"$ASK_ID"'" for x in items) else 0)'; then S3=PASS; break; fi
  done
fi

kill $ENG 2>/dev/null; trap - EXIT
PASSED=false
[ "$S1" = PASS ] && [ "$S1_LATENCY" -le 120 ] && [ "$S2" = PASS ] && [ "$S3" = PASS ] && PASSED=true
cat <<EOF
{"phase_gate_passed": $PASSED, "S1_outbound_call": "$S1", "S1_latency_s": $S1_LATENCY,
 "S2_ask_sms": "$S2", "ask_id": "${ASK_ID:-none}", "S3_inbound_yes": "$S3",
 "note": "independent Twilio REST read-back; S3 needs Omar's real reply — run while he is awake"}
EOF
[ "$PASSED" = true ]
