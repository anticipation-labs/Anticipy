#!/bin/sh
# llm_contract_local.sh — prove POST /agent/llm on a REAL workerd, with no
# vendor key and no money spent.
#
#   sh migration/workers/scripts/llm_contract_local.sh            # the wire tests
#   sh migration/workers/scripts/llm_contract_local.sh -x -vv     # extra pytest args
#
# WHAT IT DOES, in order:
#   1. stages public/ if it is missing (wrangler refuses to start without the
#      assets directory);
#   2. applies migration/d1/schema.sql to the LOCAL D1 (idempotent) and seeds
#      one paired agent with an owner_ref;
#   3. starts scripts/fake_llm_provider.py on a loopback port;
#   4. starts `wrangler dev --local` with LLM_PROVIDER_BASE pointed at the fake
#      and two FAKE vendor keys — random strings, so the "no key in any
#      response" assertion has something specific to look for;
#   5. runs migration/spec/contract_tests.py, only the /agent/llm tests, with
#      the variables that unlock the wire and D1 assertions;
#   6. tears everything down and exits with pytest's status.
#
# NOTHING HERE TOUCHES A DEPLOYED WORKER OR A REAL PROVIDER. The keys are fake,
# the provider is a Python script, and the database is .wrangler/state/.
#
# EXIT
#   0  every selected test passed
#   1  at least one failed
#   2  could not run (a port in use, wrangler never came up, missing tool)
set -u

HERE=$(cd "$(dirname "$0")/.." && pwd)          # migration/workers
cd "$HERE" || exit 2
CONFIG="$HERE/wrangler.jsonc"
PORT="${LLM_TEST_PORT:-8791}"
FAKE_PORT="${LLM_FAKE_PORT:-9797}"
LOG="${TMPDIR:-/tmp}/llm_contract_local.$$.log"

for tool in node npx python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "llm-wire: $tool not found" >&2; exit 2; }
done
[ -d node_modules/wrangler ] || { echo "llm-wire: run npm ci in migration/workers first" >&2; exit 2; }
if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "llm-wire: something already answers on :$PORT (set LLM_TEST_PORT)" >&2; exit 2
fi

[ -d public ] || npm run -s stage:assets

STAMP=$(date +%s)
NONCE=$(python3 -c 'import secrets; print(secrets.token_hex(6))')
GEMINI_FAKE="FAKE-GEMINI-KEY-$NONCE"
OPENROUTER_FAKE="FAKE-OPENROUTER-KEY-$NONCE"
AGENT_ID="contract-llm-$STAMP-$NONCE"
AGENT_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
BROWSER_MODEL="${LLM_TEST_BROWSER_MODEL:-anthropic/claude-sonnet-4.6}"   # → OpenRouter path
VISION_MODEL="${LLM_TEST_VISION_MODEL:-google/gemini-2.5-flash}"         # → Google path
NOW=$(python3 -c 'import datetime; print(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000Z"))')

d1() { CI=1 npx --no-install wrangler d1 execute DB --local --config "$CONFIG" "$@"; }

echo "llm-wire: schema → local D1"
d1 --file ../d1/schema.sql >/dev/null 2>&1 || { echo "llm-wire: schema.sql failed" >&2; exit 2; }
echo "llm-wire: seeding paired agent $AGENT_ID"
d1 --command "INSERT OR REPLACE INTO agents (id, created, updated, agent_id, agent_token, pair_code, paired, owner_ref, browser, llm_calls, llm_hour) VALUES ('llmtest$(echo "$NONCE" | cut -c1-8)', '$NOW', '$NOW', '$AGENT_ID', '$AGENT_TOKEN', '000000', 1, 'owner-contract-llm', 'conformance', 0, '')" >/dev/null 2>&1 \
  || { echo "llm-wire: seeding the agent failed" >&2; exit 2; }

python3 scripts/fake_llm_provider.py --port "$FAKE_PORT" 2>>"$LOG" &
FAKE_PID=$!

CI=1 npx --no-install wrangler dev --config "$CONFIG" --local --ip 127.0.0.1 --port "$PORT" \
  --var "LLM_PROVIDER_BASE:http://127.0.0.1:$FAKE_PORT" \
  --var "GEMINI_API_KEY:$GEMINI_FAKE" \
  --var "OPENROUTER_API_KEY:$OPENROUTER_FAKE" \
  --var "ANTICIPY_BROWSER_MODEL:$BROWSER_MODEL" \
  --var "ANTICIPY_VISION_MODEL:$VISION_MODEL" \
  --var "ANTICIPY_ENV:test" \
  >>"$LOG" 2>&1 &
DEV_PID=$!

cleanup() {
  pkill -P "$DEV_PID" >/dev/null 2>&1
  kill "$DEV_PID" "$FAKE_PID" >/dev/null 2>&1
  wait "$DEV_PID" "$FAKE_PID" 2>/dev/null
  d1 --command "DELETE FROM agents WHERE agent_id = '$AGENT_ID' OR agent_id LIKE '$AGENT_ID-%'" >/dev/null 2>&1
}
trap cleanup EXIT INT TERM

i=0
until curl -sf "http://127.0.0.1:$FAKE_PORT/health" >/dev/null 2>&1 \
   && curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 120 ]; then
    echo "llm-wire: wrangler dev or the fake provider never answered; log: $LOG" >&2
    tail -30 "$LOG" >&2
    exit 2
  fi
  sleep 0.5
done
echo "llm-wire: workerd on :$PORT, fake provider on :$FAKE_PORT, log $LOG"

BASE_URL="http://127.0.0.1:$PORT" \
ANTICIPY_TEST_AGENT_ID="$AGENT_ID" \
ANTICIPY_TEST_AGENT_TOKEN="$AGENT_TOKEN" \
ANTICIPY_TEST_LLM_FAKE_PROVIDER=1 \
ANTICIPY_TEST_LLM_KEY_SMELLS="$GEMINI_FAKE,$OPENROUTER_FAKE" \
ANTICIPY_TEST_VISION_MODEL="$VISION_MODEL" \
ANTICIPY_LOCAL_WRANGLER_CONFIG="$CONFIG" \
python3 -m pytest ../spec/contract_tests.py -p no:cacheprovider -v \
  -k "agent_llm or AgentLlm" "$@"
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
  echo "llm-wire: FAILED ($STATUS); wrangler log tail:" >&2
  tail -20 "$LOG" >&2
fi
exit "$STATUS"
