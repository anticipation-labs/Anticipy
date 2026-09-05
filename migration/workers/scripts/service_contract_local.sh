#!/bin/sh
# service_contract_local.sh — prove the three account routes, /agent/key's
# owner card and /me/delete's body on a REAL workerd, with a REAL D1, a REAL
# sign-in, and nothing deployed.
#
#   sh migration/workers/scripts/service_contract_local.sh            # the wire tests
#   sh migration/workers/scripts/service_contract_local.sh -x -vv     # extra pytest args
#
# WHY IT EXISTS. On 2026-09-05 /auth/claim, /me/phone/remove and
# /me/profile/upsert were each `verifyToken` followed by
# `503 {"ok":false,"message":"… not yet ported"}`, and the contract suite was
# GREEN on them: every test it had drove the 401 in FRONT of the stub, and the
# gate in front of a stub answers exactly like the gate in front of a route.
# The account-token half never ran, because ANTICIPY_TEST_OWNER_EMAIL was never
# set anywhere that ran it. This script sets it — against a disposable account
# on a scratch database — so the write half cannot be green while absent.
#
# WHAT IT DOES, in order (the shape of sms_contract_local.sh):
#   1. stages public/ if it is missing (wrangler refuses to start without it);
#   2. applies migration/d1/schema.sql to the LOCAL D1 (idempotent);
#   3. starts `wrangler dev --local` with a random service token, a fake
#      provider key and the two model names, so the guard is ON and /agent/key
#      has something to answer;
#   4. creates THREE disposable accounts through the real signup route —
#      A: paired to a seeded browser agent, for /agent/key's owner card;
#      B: the account the profile/phone/claim tests sign in as;
#      C: the account the destructive /me/delete test consumes —
#      and seeds A's profile plus a handful of pre-account rows carrying B's
#      legacy uuid, so /auth/claim has something real to adopt;
#   5. runs migration/spec/contract_tests.py TWICE, because the delete test
#      consumes the account it signs in as: once as B for the service and agent
#      routes, once as C for TestAccountDelete;
#   6. tears everything down and exits non-zero if either run failed.
#
# NOTHING HERE TOUCHES A DEPLOYED WORKER OR A REAL PERSON. Every address is
# @anticipy-test.invalid, every number is a 555, the provider key is a random
# string, and the database is .wrangler/state/ (the local scratch D1).
#
# EXIT
#   0  every selected test passed
#   1  at least one failed
#   2  could not run (a port in use, wrangler never came up, missing tool)
set -u

HERE=$(cd "$(dirname "$0")/.." && pwd)          # migration/workers
cd "$HERE" || exit 2
CONFIG="$HERE/wrangler.jsonc"
PORT="${SERVICE_TEST_PORT:-8794}"
INSPECTOR="${SERVICE_TEST_INSPECTOR_PORT:-9393}"
STATE="$HERE/.wrangler/state"
LOG="${TMPDIR:-/tmp}/service_contract_local.$$.log"

for tool in node npx python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "service-wire: $tool not found" >&2; exit 2; }
done
[ -d node_modules/wrangler ] || { echo "service-wire: run npm ci in migration/workers first" >&2; exit 2; }
if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "service-wire: something already answers on :$PORT (set SERVICE_TEST_PORT)" >&2; exit 2
fi

[ -d public ] || npm run -s stage:assets

NONCE=$(python3 -c 'import secrets; print(secrets.token_hex(6))')
SHORT=$(echo "$NONCE" | cut -c1-7)
SERVICE_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
GEMINI_FAKE="FAKE-GEMINI-KEY-$NONCE"
BROWSER_MODEL="${SERVICE_TEST_BROWSER_MODEL:-google/gemini-3.1-pro-preview}"
VISION_MODEL="${SERVICE_TEST_VISION_MODEL:-google/gemini-2.5-flash}"
PASSWORD="contract-suite-$NONCE"
EMAIL_A="svc-agent-$NONCE@anticipy-test.invalid"
EMAIL_B="svc-owner-$NONCE@anticipy-test.invalid"
EMAIL_C="svc-delete-$NONCE@anticipy-test.invalid"
LEGACY_A="legacy-a-$NONCE"
LEGACY_B="legacy-b-$NONCE"
LEGACY_C="legacy-c-$NONCE"
AGENT_ID="contract-service-$NONCE-agent"
AGENT_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
NOW=$(python3 -c 'import datetime; print(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000Z"))')
# Declared before the trap: cleanup names them, and `set -u` would abort the
# trap itself if the run died before the accounts were created.
OWNER_A=""; OWNER_B=""; OWNER_C=""

d1() { CI=1 npx --no-install wrangler d1 execute DB --local --config "$CONFIG" "$@"; }

echo "service-wire: schema → the local D1 under $STATE"
d1 --file ../d1/schema.sql >/dev/null 2>&1 || { echo "service-wire: schema.sql failed" >&2; exit 2; }

# The guard is ON (a service token is bound), a provider key exists so
# /agent/key does not 503, and both model names are set so the pair
# /agent/key hands out is the pair /agent/llm accepts.
CI=1 npx --no-install wrangler dev --config "$CONFIG" --local --ip 127.0.0.1 --port "$PORT" \
  --inspector-port "$INSPECTOR" \
  --var "ANTICIPY_SERVICE_TOKEN:$SERVICE_TOKEN" \
  --var "ANTICIPY_AUTH_SECRET:contract-secret-$NONCE" \
  --var "GEMINI_API_KEY:$GEMINI_FAKE" \
  --var "ANTICIPY_BROWSER_MODEL:$BROWSER_MODEL" \
  --var "ANTICIPY_VISION_MODEL:$VISION_MODEL" \
  --var "ANTICIPY_ENV:test" \
  >>"$LOG" 2>&1 &
DEV_PID=$!

# THE DEFAULT .wrangler/state, NOT A PRIVATE ONE, and that is not laziness:
# the suite's own local_d1() shells out to `wrangler d1 execute --local` with
# no --persist-to, so a private state directory would leave every D1 assertion
# reading an EMPTY second database and passing on nothing. Measured here on the
# first run: the purge-row leg failed against a `purges` table that did not
# exist, because it was looking at the other file. The rows this script makes
# are therefore deleted by name below.
cleanup() {
  pkill -P "$DEV_PID" >/dev/null 2>&1
  kill "$DEV_PID" >/dev/null 2>&1
  wait "$DEV_PID" 2>/dev/null
  for t in owner_profile jobs segments agents pendants events purges; do
    d1 --command "DELETE FROM $t WHERE owner_ref IN ('$OWNER_A', '$OWNER_B', '$OWNER_C')" >/dev/null 2>&1
  done
  d1 --command "DELETE FROM agents WHERE agent_id = '$AGENT_ID'" >/dev/null 2>&1
  d1 --command "DELETE FROM jobs WHERE owner = '$LEGACY_B'" >/dev/null 2>&1
  d1 --command "DELETE FROM segments WHERE owner = '$LEGACY_B'" >/dev/null 2>&1
  d1 --command "DELETE FROM owners WHERE id IN ('$OWNER_A', '$OWNER_B', '$OWNER_C')" >/dev/null 2>&1
}
trap cleanup EXIT INT TERM

i=0
until curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 120 ]; then
    echo "service-wire: wrangler dev never answered on :$PORT; log: $LOG" >&2
    tail -30 "$LOG" >&2
    exit 2
  fi
  sleep 0.5
done
echo "service-wire: workerd on :$PORT, log $LOG"

BASE="http://127.0.0.1:$PORT"

# Accounts are made through the REAL signup route, so the password digest and
# the tokenKey are the ones src/pb/auth.ts will later verify. Seeding them with
# SQL would prove nothing about signing in.
signup() {   # email legacy_uuid  -> prints the owners id
  curl -sf -X POST "$BASE/api/collections/owners/records" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\",\"passwordConfirm\":\"$PASSWORD\",\"legacy_uuid\":\"$2\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))'
}
OWNER_A=$(signup "$EMAIL_A" "$LEGACY_A")
OWNER_B=$(signup "$EMAIL_B" "$LEGACY_B")
OWNER_C=$(signup "$EMAIL_C" "$LEGACY_C")
[ -n "$OWNER_A" ] && [ -n "$OWNER_B" ] && [ -n "$OWNER_C" ] || {
  echo "service-wire: could not create the disposable accounts" >&2; tail -20 "$LOG" >&2; exit 2; }
echo "service-wire: owners A=$OWNER_A (agent) B=$OWNER_B (routes) C=$OWNER_C (delete)"

# A paired agent for owner A, and A's profile, so /agent/key answers a
# POPULATED owner card rather than the legitimate `null`.
d1 --command "INSERT OR REPLACE INTO agents (id, created, updated, agent_id, agent_token, pair_code, paired, owner_ref, browser, llm_calls, llm_hour) VALUES ('svcagent$SHORT', '$NOW', '$NOW', '$AGENT_ID', '$AGENT_TOKEN', '900001', 1, '$OWNER_A', 'conformance', 0, '')" >/dev/null 2>&1 \
  && d1 --command "INSERT OR REPLACE INTO owner_profile (id, created, updated, owner_id, owner_ref, first_name, last_name, email, phone, birthday, facts, timezone) VALUES ('svcprof0$SHORT', '$NOW', '$NOW', '$LEGACY_A', '$OWNER_A', 'Ada', 'Lovelace', '$EMAIL_A', '+15550100701', '1815-12-10', '{}', 'America/Vancouver')" >/dev/null 2>&1 \
  || { echo "service-wire: seeding the agent/profile failed" >&2; exit 2; }

# Pre-account rows carrying B's legacy uuid, so /auth/claim has real work.
d1 --command "INSERT OR REPLACE INTO jobs (id, created, updated, goal, status, owner, owner_ref) VALUES ('svcjob00$SHORT', '$NOW', '$NOW', 'book a table', 'queued', '$LEGACY_B', '')" >/dev/null 2>&1
d1 --command "INSERT OR REPLACE INTO segments (id, created, updated, status, owner, owner_ref) VALUES ('svcseg00$SHORT', '$NOW', '$NOW', 'open', '$LEGACY_B', '')" >/dev/null 2>&1

run_suite() {   # email password extra-pytest-selector...
  email=$1; shift
  BASE_URL="$BASE" \
  ANTICIPY_SERVICE_TOKEN="$SERVICE_TOKEN" \
  ANTICIPY_TEST_OWNER_EMAIL="$email" \
  ANTICIPY_TEST_OWNER_PASSWORD="$PASSWORD" \
  ANTICIPY_TEST_AGENT_ID="$AGENT_ID" \
  ANTICIPY_TEST_AGENT_TOKEN="$AGENT_TOKEN" \
  ANTICIPY_LOCAL_WRANGLER_CONFIG="$CONFIG" \
  ANTICIPY_ALLOW_DESTRUCTIVE=1 \
  python3 -m pytest ../spec/contract_tests.py -p no:cacheprovider -v "$@"
}

# 1. The service routes and the agent routes, signed in as B.
#
# TWO LEGS ARE NOT SELECTED, AND NEITHER IS EXCLUDED FOR BEING INCONVENIENT.
# This script is the first thing in the tree that ever sets
# ANTICIPY_TEST_OWNER_EMAIL against the Worker, so it is the first thing that
# has ever RUN the account half of the suite -- and it found two Worker
# divergences from CONTRACT.md that belong to other files and other people:
#
#   TestServiceRoutes::test_transcription_tokens_are_410_for_a_signed_in_caller
#     §6.13 says a signed-in caller gets 410 {"error":"transcription tokens
#     are not issued", "reason":"raw audio never leaves a device …"}. The
#     Worker's transcriptionToken (src/routes/sms.ts:154-159) ignores the
#     Authorization header entirely and answers 401 to everyone. Measured
#     here: 401 {"ok":false,"message":"Sign in first."} with a valid token.
#
#   TestAgentRoutes::test_captcha_never_solves_a_protected_host
#     §6.5 says an unconfigured instance answers 501 {"error":"solving is not
#     configured"}, which is the status the test skips on. The Worker's
#     agentCaptcha answers 503 {"error":"captcha solving is not configured"},
#     so the test runs on and fails. Both the status and the sentence differ.
#
# Neither is in this cluster's remit (F01/F02/F03/F14/F40), and softening a
# test to cover somebody else's route is how a port looks finished. They are
# named here rather than deleted, and the selection below is POSITIVE: what
# this script claims to prove.
run_suite "$EMAIL_B" -k "(TestServiceRoutes and not transcription_tokens_are_410) \
or test_agent_key or test_registration or test_agent_llm_refuses_a_model" "$@"
STATUS_ROUTES=$?

# 2. The delete, signed in as C — it consumes the account, so it cannot share
#    the session-scoped `account` fixture with anything above.
run_suite "$EMAIL_C" -k "TestAccountDelete" "$@"
STATUS_DELETE=$?

STATUS=0
[ "$STATUS_ROUTES" -eq 0 ] || STATUS=1
[ "$STATUS_DELETE" -eq 0 ] || STATUS=1

if [ "$STATUS" -ne 0 ]; then
  echo "service-wire: FAILED (routes=$STATUS_ROUTES delete=$STATUS_DELETE); wrangler log tail:" >&2
  tail -20 "$LOG" >&2
fi
exit "$STATUS"
