#!/usr/bin/env bash
# Owner app auth gate: a public Next deploy must not relay private owner routes
# unless the owner has unlocked the app session.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${ANTICIPY_TEST_OWNER_APP_PORT:-3197}"
BASE="http://127.0.0.1:${PORT}"
TOKEN="owner-public-token"
COOKIE_JAR="$(mktemp -t anticipy-owner-cookie-XXXXXX)"
BODY="$(mktemp -t anticipy-owner-body-XXXXXX)"
LOG="$(mktemp -t anticipy-owner-next-XXXXXX.log)"
PID=""

cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  rm -f "$COOKIE_JAR" "$BODY" "$LOG"
}
trap cleanup EXIT

cd "$REPO"
ANTICIPY_APP_OWNER_TOKEN="$TOKEN" \
ANTICIPY_ENGINE_URL="http://127.0.0.1:9" \
npm run dev -- --hostname 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
PID="$!"

ready=0
for _ in $(seq 1 80); do
  if curl -fsS "$BASE/api/owner/session" >"$BODY" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 0.25
done
if [ "$ready" -ne 1 ]; then
  echo "Next test server did not become ready"
  cat "$LOG"
  exit 1
fi

code="$(curl -sS -o "$BODY" -w "%{http_code}" "$BASE/api/status")"
test "$code" = "401"
grep -q '"owner_auth_required"' "$BODY"

code="$(curl -sS -o "$BODY" -w "%{http_code}" \
  -H "content-type: application/json" \
  -d '{"token":"wrong"}' \
  "$BASE/api/owner/session")"
test "$code" = "401"
grep -q '"owner_auth_failed"' "$BODY"

code="$(curl -sS -c "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" \
  -H "content-type: application/json" \
  -d "{\"token\":\"$TOKEN\"}" \
  "$BASE/api/owner/session")"
test "$code" = "200"
grep -q '"authenticated":true' "$BODY"

code="$(curl -sS -b "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" "$BASE/api/status")"
test "$code" = "503"
grep -q '"engine_unreachable"' "$BODY"

code="$(curl -sS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" -X DELETE "$BASE/api/owner/session")"
test "$code" = "200"

code="$(curl -sS -b "$COOKIE_JAR" -o "$BODY" -w "%{http_code}" "$BASE/api/status")"
test "$code" = "401"
grep -q '"owner_auth_required"' "$BODY"

echo "PASS owner_app_auth: Next app routes require owner session when token is configured"
