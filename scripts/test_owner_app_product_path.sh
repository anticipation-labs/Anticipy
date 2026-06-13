#!/usr/bin/env bash
# Public owner app product path: unlock -> Press Go route -> live engine -> cards.
# This does not call the engine directly for the product action. It uses the same
# Next API route the UI uses, with app-session auth and engine-token auth enabled.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/engine/.venv/bin/python"
HOST=127.0.0.1
ENGINE_PORT="${ANTICIPY_TEST_PRODUCT_ENGINE_PORT:-8798}"
NEXT_PORT="${ANTICIPY_TEST_PRODUCT_NEXT_PORT:-3198}"
ENGINE_BASE="http://$HOST:$ENGINE_PORT"
NEXT_BASE="http://$HOST:$NEXT_PORT"
APP_TOKEN="owner-app-product-token"
ENGINE_TOKEN="owner-engine-product-token"
DATA_DIR="$(mktemp -d -t anticipy-owner-product-XXXXXX)"
COOKIE_JAR="$(mktemp -t anticipy-owner-product-cookie-XXXXXX)"
PAYLOAD="$(mktemp -t anticipy-owner-product-payload-XXXXXX.json)"
BODY="$(mktemp -t anticipy-owner-product-body-XXXXXX.json)"
UPLOAD_ROOT="$(mktemp -d -t anticipy-owner-product-upload-XXXXXX)"
UPLOAD_FILE="$(mktemp -t anticipy-owner-product-upload-XXXXXX.txt)"
ENGINE_LOG="$(mktemp -t anticipy-owner-product-engine-XXXXXX.log)"
NEXT_LOG="$(mktemp -t anticipy-owner-product-next-XXXXXX.log)"
ENGINE_PID=""
NEXT_PID=""

cleanup() {
  if [ -n "$NEXT_PID" ] && kill -0 "$NEXT_PID" >/dev/null 2>&1; then
    kill "$NEXT_PID" >/dev/null 2>&1 || true
    wait "$NEXT_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$ENGINE_PID" ] && kill -0 "$ENGINE_PID" >/dev/null 2>&1; then
    kill "$ENGINE_PID" >/dev/null 2>&1 || true
    wait "$ENGINE_PID" >/dev/null 2>&1 || true
  fi
  rm -f "$COOKIE_JAR" "$PAYLOAD" "$BODY" "$UPLOAD_FILE" "$ENGINE_LOG" "$NEXT_LOG"
  rm -rf "$UPLOAD_ROOT"
}
trap cleanup EXIT

if lsof -nP -iTCP:"$ENGINE_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "engine test port $ENGINE_PORT busy" >&2
  exit 1
fi
if lsof -nP -iTCP:"$NEXT_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "next test port $NEXT_PORT busy" >&2
  exit 1
fi

cd "$REPO"
ANTICIPY_DATA_DIR="$DATA_DIR" \
ANTICIPY_MODEL_PROVIDER=stub \
ANTICIPY_HANDS_MODE=mock \
ANTICIPY_NATIVE_BRIDGE_FALLBACK=0 \
ANTICIPY_TICK_SECONDS=0 \
ANTICIPY_INBOUND_POLL_SECONDS=0 \
ANTICIPY_OWNER_API_TOKEN="$ENGINE_TOKEN" \
ANTICIPY_UPLOAD_ROOT="$UPLOAD_ROOT" \
"$PY" -m uvicorn --app-dir "$REPO/engine" anticipy_engine.main:app \
  --host "$HOST" --port "$ENGINE_PORT" --log-level warning >"$ENGINE_LOG" 2>&1 &
ENGINE_PID="$!"

engine_ready=0
for _ in $(seq 1 80); do
  if curl -fsS "$ENGINE_BASE/health" >/dev/null 2>&1; then
    engine_ready=1
    break
  fi
  sleep 0.25
done
if [ "$engine_ready" -ne 1 ]; then
  echo "Engine test server did not become ready" >&2
  cat "$ENGINE_LOG" >&2
  exit 1
fi

ANTICIPY_APP_OWNER_TOKEN="$APP_TOKEN" \
ANTICIPY_OWNER_API_TOKEN="$ENGINE_TOKEN" \
ANTICIPY_ENGINE_URL="$ENGINE_BASE" \
ANTICIPY_UPLOAD_ROOT="$UPLOAD_ROOT" \
npm run dev -- --hostname "$HOST" --port "$NEXT_PORT" >"$NEXT_LOG" 2>&1 &
NEXT_PID="$!"

ready=0
for _ in $(seq 1 80); do
  if curl -fsS "$NEXT_BASE/api/owner/session" >"$BODY" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.25
done
if [ "$ready" -ne 1 ]; then
  echo "Next test server did not become ready" >&2
  cat "$NEXT_LOG" >&2
  exit 1
fi

code="$(curl -sS -o "$BODY" -w "%{http_code}" "$NEXT_BASE/api/status")"
test "$code" = "401"
grep -q '"owner_auth_required"' "$BODY"

code="$(curl -sS -c "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" \
  -H "content-type: application/json" \
  -d "{\"token\":\"$APP_TOKEN\"}" \
  "$NEXT_BASE/api/owner/session")"
test "$code" = "200"
grep -q '"authenticated":true' "$BODY"

code="$(curl -sS -o "$BODY" -w "%{http_code}" "$ENGINE_BASE/status")"
test "$code" = "401"

cat >"$PAYLOAD" <<'JSON'
{
  "source": "typed",
  "execute_actions": true,
  "meta": {"test": "owner_app_product_path"},
  "text": "[08:01] Omar: yeah yeah whatever, this week is cooked.\n[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.\n[08:05] Omar: oh sure, I will just clone myself, that will fix the schedule.\n[09:12] Sam needs the revised deck before Friday; I told him I would send it.\n[10:17] I was comparing compact label makers at Staples; liked the Brother cube one.\n[10:22] That label thing I liked at Staples, cart it so I can check shipping later, no buying.\n[11:33] That random gadget thing, put it in the cart if it looks right, don't buy it.\n[12:10] order the replacement filter today and just pay whatever it costs.\n[13:00] My wife Maya prefers texts after lunch."
}
JSON

code="$(curl -sS -b "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" \
  -H "content-type: application/json" \
  --data-binary "@$PAYLOAD" \
  "$NEXT_BASE/api/owner/ingest")"
test "$code" = "200"

"$PY" - "$BODY" <<'PY'
import json
import sys

body = json.load(open(sys.argv[1], encoding="utf-8"))
cards = body["cards"]

def one(needle):
    matches = [c for c in cards if needle.lower() in c["source_text"].lower()]
    assert len(matches) == 1, (needle, matches, cards)
    return matches[0]

pickup = one("pickup to 3")
assert pickup["status"] == "done", pickup

send = one("Sam needs")
assert send["status"] == "waiting" and send["execution"]["ask_id"], send

resolved_cart = one("label thing")
assert resolved_cart["status"] == "done", resolved_cart
assert any(p.get("type") == "memory_resolution" for p in resolved_cart["proof"]), resolved_cart

unresolved_cart = one("random gadget")
assert unresolved_cart["status"] == "waiting", unresolved_cart
assert unresolved_cart["execution"]["decision"] == "ask", unresolved_cart

money = one("pay whatever")
assert money["status"] == "blocked", money
assert money["execution"]["goal_id"] is None and money["execution"]["ask_id"] is None, money

profile = one("prefers texts")
assert profile["status"] == "done", profile

assert body["ignored_line_count"] >= 3, body
PY

code="$(curl -sS -b "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" "$NEXT_BASE/api/owner/cards?limit=20")"
test "$code" = "200"
"$PY" - "$BODY" <<'PY'
import json
import sys

cards = json.load(open(sys.argv[1], encoding="utf-8"))["cards"]
statuses = {c["source_text"]: c["status"] for c in cards}
assert any("label thing" in text and status == "done" for text, status in statuses.items()), statuses
assert any("random gadget" in text and status == "waiting" for text, status in statuses.items()), statuses
assert any("pay whatever" in text and status == "blocked" for text, status in statuses.items()), statuses
PY

code="$(curl -sS -b "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" "$NEXT_BASE/api/status")"
test "$code" = "200"
grep -q '"owner_api":{"state":"protected"' "$BODY"

cat >"$UPLOAD_FILE" <<'TEXT'
[14:00] Omar: was comparing travel umbrellas at Target; liked the black compact travel umbrella.
[14:05] That umbrella thing at Target, cart it so I can compare shipping later, no checkout.
[15:00] Nora needs the launch notes before Monday; I told her I would send them.
[15:20] pay the overdue thing now with card.
TEXT

code="$(curl -sS -b "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" \
  -F "file=@$UPLOAD_FILE;filename=uploaded-day.txt" \
  -F "source=upload" \
  -F "execute_actions=true" \
  "$NEXT_BASE/api/owner/upload")"
test "$code" = "200"

"$PY" - "$BODY" <<'PY'
import json
import sys

body = json.load(open(sys.argv[1], encoding="utf-8"))
cards = body["cards"]

def one(needle):
    matches = [c for c in cards if needle.lower() in c["source_text"].lower()]
    assert len(matches) == 1, (needle, matches, cards)
    return matches[0]

umbrella = one("umbrella thing")
assert umbrella["status"] == "done", umbrella
assert any(p.get("type") == "memory_resolution" for p in umbrella["proof"]), umbrella

nora = one("Nora needs")
assert nora["status"] == "waiting" and nora["execution"]["ask_id"], nora

money = one("overdue thing")
assert money["status"] == "blocked", money
assert money["execution"]["goal_id"] is None and money["execution"]["ask_id"] is None, money
PY

if find "$UPLOAD_ROOT" -mindepth 1 -print -quit | grep -q .; then
  echo "upload staging root was not cleaned" >&2
  find "$UPLOAD_ROOT" -mindepth 1 -maxdepth 3 -print >&2
  exit 1
fi

echo "PASS owner_app_product_path: owner unlock -> Next Press Go/upload routes -> protected engine -> messy cards"
