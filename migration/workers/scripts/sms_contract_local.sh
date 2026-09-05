#!/bin/sh
# sms_contract_local.sh — prove POST /sms/sendblue and POST /sms/inbound on a
# REAL workerd, with no carrier, no real number and no real secret.
#
#   sh migration/workers/scripts/sms_contract_local.sh            # the wire tests
#   sh migration/workers/scripts/sms_contract_local.sh -x -vv     # extra pytest args
#
# WHAT IT DOES, in order (the shape of llm_contract_local.sh):
#   1. stages public/ if it is missing (wrangler refuses to start without it);
#   2. applies migration/d1/schema.sql to the LOCAL D1 (idempotent) and seeds
#      three disposable owners: one whose profile carries OWNER_PHONE, and two
#      whose profiles both carry AMBIG_PHONE — the shared-number case;
#   3. starts `wrangler dev --local` CONFIGURED: a random Sendblue webhook
#      secret, a Sendblue number, a random Twilio auth token, an account SID
#      and a Twilio number — so both front doors and both allowlists are real;
#   4. starts a SECOND `wrangler dev --local` with NO Sendblue secret at all,
#      on its own port and its own persist dir, for the one leg that needs an
#      unconfigured Worker: "unset secret is a 503, not a 403";
#   5. runs migration/spec/contract_tests.py, the Sendblue and Twilio inbound
#      tests only, with the variables that unlock the write and D1 assertions
#      (ANTICIPY_ALLOW_DESTRUCTIVE=1 is set because the rows written are in
#      .wrangler/state and nowhere else);
#   6. tears everything down, deletes the seeded rows, exits with pytest's status.
#
# NOTHING HERE TOUCHES A DEPLOYED WORKER, A CARRIER OR A REAL PHONE. The
# secrets are random, the numbers are 555s, and the database is .wrangler/state/.
#
# EXIT
#   0  every selected test passed
#   1  at least one failed
#   2  could not run (a port in use, wrangler never came up, missing tool)
set -u

HERE=$(cd "$(dirname "$0")/.." && pwd)          # migration/workers
cd "$HERE" || exit 2
CONFIG="$HERE/wrangler.jsonc"
PORT="${SMS_TEST_PORT:-8792}"
BARE_PORT="${SMS_TEST_BARE_PORT:-8793}"
INSPECTOR="${SMS_TEST_INSPECTOR_PORT:-9391}"
BARE_INSPECTOR="${SMS_TEST_BARE_INSPECTOR_PORT:-9392}"
BARE_STATE="$HERE/.wrangler/state-sms-bare"
LOG="${TMPDIR:-/tmp}/sms_contract_local.$$.log"

for tool in node npx python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "sms-wire: $tool not found" >&2; exit 2; }
done
[ -d node_modules/wrangler ] || { echo "sms-wire: run npm ci in migration/workers first" >&2; exit 2; }
for p in "$PORT" "$BARE_PORT"; do
  if curl -sf "http://127.0.0.1:$p/api/health" >/dev/null 2>&1; then
    echo "sms-wire: something already answers on :$p (set SMS_TEST_PORT / SMS_TEST_BARE_PORT)" >&2; exit 2
  fi
done

[ -d public ] || npm run -s stage:assets

NONCE=$(python3 -c 'import secrets; print(secrets.token_hex(6))')
SHORT=$(echo "$NONCE" | cut -c1-7)
SENDBLUE_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
TWILIO_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
TWILIO_SID="AC$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
SENDBLUE_NUMBER="+15550100999"
TWILIO_NUMBER="+15550100998"
OWNER_PHONE="+15550100001"
AMBIG_PHONE="+15550100002"
OWNER_ID="smsowner$SHORT"                       # 15 chars, PocketBase-shaped
AMBIG_A="smsambga$SHORT"
AMBIG_B="smsambgb$SHORT"
NOW=$(python3 -c 'import datetime; print(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000Z"))')

d1() { CI=1 npx --no-install wrangler d1 execute DB --local --config "$CONFIG" "$@"; }

echo "sms-wire: schema → local D1"
d1 --file ../d1/schema.sql >/dev/null 2>&1 || { echo "sms-wire: schema.sql failed" >&2; exit 2; }
echo "sms-wire: seeding owner $OWNER_ID ($OWNER_PHONE) and the ambiguous pair ($AMBIG_PHONE)"
seed_owner() {   # id email
  d1 --command "INSERT OR REPLACE INTO owners (id, created, updated, email, emailVisibility, verified, password, tokenKey, phone, legacy_uuid) VALUES ('$1', '$NOW', '$NOW', '$2', 0, 0, '', '', '', '')" >/dev/null 2>&1
}
seed_profile() { # id owner_ref phone
  d1 --command "INSERT OR REPLACE INTO owner_profile (id, created, updated, owner_id, phone, owner_ref) VALUES ('$1', '$NOW', '$NOW', 'legacy-$1', '$3', '$2')" >/dev/null 2>&1
}
seed_owner "$OWNER_ID" "sms-contract-$NONCE@anticipy-test.invalid" \
  && seed_profile "smsprof0$SHORT" "$OWNER_ID" "$OWNER_PHONE" \
  && seed_owner "$AMBIG_A" "sms-ambig-a-$NONCE@anticipy-test.invalid" \
  && seed_profile "smsprofa$SHORT" "$AMBIG_A" "$AMBIG_PHONE" \
  && seed_owner "$AMBIG_B" "sms-ambig-b-$NONCE@anticipy-test.invalid" \
  && seed_profile "smsprofb$SHORT" "$AMBIG_B" "$AMBIG_PHONE" \
  || { echo "sms-wire: seeding failed" >&2; exit 2; }

# ANTICIPY_TWILIO_WEBHOOK_URL IS PINNED HERE, AND IT IS NOT OPTIONAL. Under
# `wrangler dev --local` the Worker sees request.url under the ROUTE's custom
# domain — http://api.anticipy.ai/sms/inbound — not the 127.0.0.1:PORT the
# suite actually posted to, so an HMAC over request.url never matches what the
# suite signed (measured 2026-09-05: every signed leg 403 "signature mismatch",
# the log naming the rewritten URL). On the deployed custom domain request.url
# IS the URL Twilio called, so the pin is a rig concern; the suite signs for
# BASE_URL + /sms/inbound, which is what this pins.
CI=1 npx --no-install wrangler dev --config "$CONFIG" --local --ip 127.0.0.1 --port "$PORT" \
  --inspector-port "$INSPECTOR" \
  --var "SENDBLUE_WEBHOOK_SECRET:$SENDBLUE_SECRET" \
  --var "SENDBLUE_FROM_NUMBER:$SENDBLUE_NUMBER" \
  --var "TWILIO_AUTH_TOKEN:$TWILIO_TOKEN" \
  --var "TWILIO_ACCOUNT_SID:$TWILIO_SID" \
  --var "TWILIO_PHONE_NUMBER:$TWILIO_NUMBER" \
  --var "ANTICIPY_TWILIO_WEBHOOK_URL:http://127.0.0.1:$PORT/sms/inbound" \
  --var "ANTICIPY_ENV:test" \
  >>"$LOG" 2>&1 &
DEV_PID=$!

# The bare Worker: no Sendblue secret, no Twilio token. Its own persist dir so
# it never opens the seeded database; the only leg it serves is the 503.
CI=1 npx --no-install wrangler dev --config "$CONFIG" --local --ip 127.0.0.1 --port "$BARE_PORT" \
  --inspector-port "$BARE_INSPECTOR" --persist-to "$BARE_STATE" \
  --var "ANTICIPY_ENV:test" \
  >>"$LOG" 2>&1 &
BARE_PID=$!

cleanup() {
  pkill -P "$DEV_PID" >/dev/null 2>&1
  pkill -P "$BARE_PID" >/dev/null 2>&1
  kill "$DEV_PID" "$BARE_PID" >/dev/null 2>&1
  wait "$DEV_PID" "$BARE_PID" 2>/dev/null
  d1 --command "DELETE FROM events WHERE owner_ref IN ('$OWNER_ID', '$AMBIG_A', '$AMBIG_B')" >/dev/null 2>&1
  d1 --command "DELETE FROM owner_profile WHERE owner_ref IN ('$OWNER_ID', '$AMBIG_A', '$AMBIG_B')" >/dev/null 2>&1
  d1 --command "DELETE FROM owners WHERE id IN ('$OWNER_ID', '$AMBIG_A', '$AMBIG_B')" >/dev/null 2>&1
  rm -rf "$BARE_STATE"
}
trap cleanup EXIT INT TERM

i=0
until curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 \
   && curl -sf "http://127.0.0.1:$BARE_PORT/api/health" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 120 ]; then
    echo "sms-wire: wrangler dev never answered on :$PORT and :$BARE_PORT; log: $LOG" >&2
    tail -30 "$LOG" >&2
    exit 2
  fi
  sleep 0.5
done
echo "sms-wire: configured workerd on :$PORT, bare workerd on :$BARE_PORT, log $LOG"

BASE_URL="http://127.0.0.1:$PORT" \
ANTICIPY_TEST_SMS_UNCONFIGURED_URL="http://127.0.0.1:$BARE_PORT" \
ANTICIPY_TEST_SENDBLUE_SECRET="$SENDBLUE_SECRET" \
ANTICIPY_TEST_SENDBLUE_NUMBER="$SENDBLUE_NUMBER" \
ANTICIPY_TEST_SMS_OWNER_REF="$OWNER_ID" \
ANTICIPY_TEST_SMS_OWNER_PHONE="$OWNER_PHONE" \
ANTICIPY_TEST_SMS_AMBIGUOUS_PHONE="$AMBIG_PHONE" \
ANTICIPY_TEST_TWILIO_AUTH_TOKEN="$TWILIO_TOKEN" \
ANTICIPY_TEST_TWILIO_ACCOUNT_SID="$TWILIO_SID" \
ANTICIPY_TEST_TWILIO_NUMBER="$TWILIO_NUMBER" \
ANTICIPY_LOCAL_WRANGLER_CONFIG="$CONFIG" \
ANTICIPY_ALLOW_DESTRUCTIVE=1 \
python3 -m pytest ../spec/contract_tests.py -p no:cacheprovider -v \
  -k "Sendblue or SmsInbound" "$@"
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
  echo "sms-wire: FAILED ($STATUS); wrangler log tail:" >&2
  tail -20 "$LOG" >&2
fi
exit "$STATUS"
