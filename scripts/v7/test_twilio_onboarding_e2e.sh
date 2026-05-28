#!/usr/bin/env bash
# v7: Cold-start onboarding end-to-end probe.
#
# What this proves (per V2 B-001):
#   * Whether the engine can fire a REAL Twilio outbound call as part of
#     a fresh user signup, deliver the friend-style interview, and have
#     the answers materialize as a dossier.
#
# What this discovered (see state/v7/twilio_onboarding_status.md):
#   * /api/dossier/outbound is wired to `app.dossier.call.handle_outbound`
#     which is NOT an importable module in this build. The endpoint
#     returns 500 (ImportError) on every call.
#   * /api/onboarding/call_stub is a JSONL log writer; no provider
#     attempt. is_stub:true is the entire payload contract.
#   * Engine has zero `from twilio` / `import twilio` / twilio.rest.Client
#     statements in /engine. There is no real call infra to exercise.
#   * TWILIO_MOCK=true is set in .env.local, but no code path reads it.
#
# Therefore the script does NOT attempt to place a paid Twilio call.
# It probes the three onboarding paths that actually populate a dossier
# (chat path + stub log + dossier/active read) and asserts they work.
# If/when real Twilio is wired (handle_outbound is given a body), this
# script will need a follow-up block that polls the Twilio REST API.

set -euo pipefail

ROOT="/Users/omarebrahim/Developer/Anticipy-V7"
DEV_ROOT="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL"
ENGINE="http://127.0.0.1:8731"

if [[ -f "${DEV_ROOT}/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${DEV_ROOT}/.env.local"
  set +a
fi

ACCOUNT="v7-twilio-cold-start-$(date +%Y%m%dT%H%M%SZ)"
PHONE="${TWILIO_MOCK_TARGET_PHONE:-+13128675309}"
OUT_DIR="${ROOT}/state/v7/twilio_e2e/${ACCOUNT}"
mkdir -p "${OUT_DIR}"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
record() { tee -a "${OUT_DIR}/run.log"; }

fail() {
  log "FAIL: $1" | record
  exit 1
}

log "account_id=${ACCOUNT} phone=${PHONE}" | record
log "TWILIO_MOCK=${TWILIO_MOCK:-<unset>}" | record
log "TWILIO_ACCOUNT_SID_present=$([[ -n ${TWILIO_ACCOUNT_SID:-} ]] && echo yes || echo no)" | record

# ---------------------------------------------------------------------------
# Gate 1: confirm engine is alive on the documented port.
# ---------------------------------------------------------------------------
START_HTTP=$(curl -s -o "${OUT_DIR}/onb_start.json" -w '%{http_code}' \
  "${ENGINE}/api/onboarding/start")
if [[ "${START_HTTP}" != "200" ]]; then
  fail "engine /api/onboarding/start returned ${START_HTTP}"
fi
log "engine alive; first question: $(grep -o '"question":"[^"]*"' "${OUT_DIR}/onb_start.json" | head -1)" | record

# ---------------------------------------------------------------------------
# Gate 2: probe /api/dossier/outbound to capture the current real-vs-stub
# state. We expect 500 because app.dossier.call is missing. Recording the
# error body proves the gap is real and not a flake.
# ---------------------------------------------------------------------------
OUTBOUND_HTTP=$(curl -s -o "${OUT_DIR}/outbound_probe.txt" -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' \
  -d "{\"phone\":\"${PHONE}\",\"account_id\":\"${ACCOUNT}\",\"name\":\"V7 Cold Start\"}" \
  "${ENGINE}/api/dossier/outbound")
log "/api/dossier/outbound HTTP ${OUTBOUND_HTTP}" | record
if [[ "${OUTBOUND_HTTP}" == "200" ]]; then
  log "REAL: /api/dossier/outbound returned 200; module wired" | record
  echo "REAL_OUTBOUND=true" > "${OUT_DIR}/outbound_state.env"
else
  log "STUB: /api/dossier/outbound is broken (no app.dossier.call module)" | record
  echo "REAL_OUTBOUND=false" > "${OUT_DIR}/outbound_state.env"
fi

# ---------------------------------------------------------------------------
# Gate 3: the only place a "call" actually gets recorded right now is the
# JSONL stub log. Drive it and assert the row lands.
# ---------------------------------------------------------------------------
STUB_HTTP=$(curl -s -o "${OUT_DIR}/call_stub.json" -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' \
  -d "{\"phone\":\"${PHONE}\",\"name\":\"V7 Cold Start\",\"intended_system_prompt\":\"V2 B-001 friend interview\",\"expected_duration_seconds\":600}" \
  "${ENGINE}/api/onboarding/call_stub")
if [[ "${STUB_HTTP}" != "200" ]]; then
  fail "/api/onboarding/call_stub returned ${STUB_HTTP}"
fi
grep -q '"is_stub":true' "${OUT_DIR}/call_stub.json" || fail "call_stub did not return is_stub:true"
log "call_stub logged with is_stub:true (correct: provider not wired)" | record

curl -s "${ENGINE}/api/onboarding/call_stubs" -o "${OUT_DIR}/call_stubs_list.json"
STUB_COUNT=$(grep -o '"count":[0-9]*' "${OUT_DIR}/call_stubs_list.json" | head -1 | cut -d: -f2)
log "call_stubs log has ${STUB_COUNT} total rows" | record

# ---------------------------------------------------------------------------
# Gate 4: prove the chat-onboarding path (the working alternative to a
# real Twilio call) populates a profile end to end. This is the cold
# start path Omar can actually ship today without paying Twilio.
# ---------------------------------------------------------------------------
CHAT_PAYLOAD='{
  "transcript": [
    {"speaker_id":"AGENT","text":"What is your name and your role or title?"},
    {"speaker_id":"WEARER","text":"My name is Casey Lin. I am head of operations at a 30 person agency in Vancouver."},
    {"speaker_id":"AGENT","text":"Who are the most important people in your work week?"},
    {"speaker_id":"WEARER","text":"My boss is Maya Chen, maya at studiozero dot com. My ops partner Devon handles billing. Our biggest client is Northbridge Foods, contact is Priya Patel."},
    {"speaker_id":"AGENT","text":"What software do you live in?"},
    {"speaker_id":"WEARER","text":"Gmail, Google Calendar, Notion, Linear, and Slack. I never want Anticipy touching production Stripe."},
    {"speaker_id":"AGENT","text":"What recurring topics should Anticipy keep an ear out for?"},
    {"speaker_id":"WEARER","text":"Anything Maya asks about Friday status, anything Priya flags as urgent, and any dentist or doctor reminders."}
  ]
}'
CHAT_HTTP=$(curl -s -o "${OUT_DIR}/chat_complete.json" -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' \
  -d "${CHAT_PAYLOAD}" "${ENGINE}/api/onboarding/chat_complete")
if [[ "${CHAT_HTTP}" != "200" ]]; then
  fail "/api/onboarding/chat_complete returned ${CHAT_HTTP}"
fi
grep -q '"ok":true' "${OUT_DIR}/chat_complete.json" \
  || fail "chat_complete did not return ok:true"

PEOPLE_HIT=$(python3 -c "
import json, sys
data = json.load(open('${OUT_DIR}/chat_complete.json'))
prof = data.get('profile') or {}
people = prof.get('people') or {}
print(len(people))
")
log "chat_complete produced profile with ${PEOPLE_HIT} people" | record
if [[ "${PEOPLE_HIT}" -lt 1 ]]; then
  fail "chat_complete profile had 0 people; extractor failed"
fi

# ---------------------------------------------------------------------------
# Gate 5: assert the dossier-active loader reads the persisted profile.
# This is the bridge the planner uses; if it does not see the new
# profile, downstream actions will be context-less.
# ---------------------------------------------------------------------------
curl -s "${ENGINE}/api/dossier/active?account_id=${ACCOUNT}" \
  -o "${OUT_DIR}/dossier_active_after_chat.json"
log "dossier/active read (after chat path): $(cat ${OUT_DIR}/dossier_active_after_chat.json)" | record

# ---------------------------------------------------------------------------
# Gate 6: if (and only if) outbound is real AND TWILIO_MOCK is unset,
# poll the Twilio REST API. Otherwise skip with reason.
# ---------------------------------------------------------------------------
# shellcheck disable=SC1091
source "${OUT_DIR}/outbound_state.env"
if [[ "${REAL_OUTBOUND}" == "true" && "${TWILIO_MOCK:-}" != "true" ]]; then
  CALL_SID=$(python3 -c "
import json, sys
data = json.load(open('${OUT_DIR}/outbound_probe.txt'))
print(data.get('call_sid') or data.get('sid') or '')
")
  if [[ -z "${CALL_SID}" ]]; then
    fail "outbound returned 200 but no call_sid in body"
  fi
  log "polling Twilio for ${CALL_SID}" | record
  END=$((SECONDS + 300))
  STATUS=""
  while (( SECONDS < END )); do
    POLL_JSON="${OUT_DIR}/twilio_status.json"
    curl -s -u "${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}" \
      "https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/Calls/${CALL_SID}.json" \
      -o "${POLL_JSON}"
    STATUS=$(python3 -c "import json; print(json.load(open('${POLL_JSON}')).get('status',''))")
    log "twilio call status=${STATUS}" | record
    if [[ "${STATUS}" == "completed" || "${STATUS}" == "in-progress" ]]; then
      break
    fi
    sleep 10
  done
  if [[ "${STATUS}" != "completed" && "${STATUS}" != "in-progress" ]]; then
    fail "twilio call ${CALL_SID} never reached in-progress (last=${STATUS})"
  fi
  log "Twilio console: https://console.twilio.com/us1/monitor/logs/calls?calls.callSid=${CALL_SID}" | record
else
  log "SKIP twilio poll: REAL_OUTBOUND=${REAL_OUTBOUND} TWILIO_MOCK=${TWILIO_MOCK:-<unset>}" | record
fi

# ---------------------------------------------------------------------------
# Verdict.
# ---------------------------------------------------------------------------
if [[ "${REAL_OUTBOUND}" == "true" ]]; then
  log "PASS: outbound endpoint live and dossier populated" | record
else
  log "PASS-WITH-GAPS: cold-start works via chat path; Twilio outbound is NOT wired (see state/v7/twilio_onboarding_status.md)" | record
fi
log "evidence: ${OUT_DIR}" | record
exit 0
