#!/usr/bin/env bash
#
# verify-deploy.sh — push the current commit to main, wait for Vercel,
# verify the live anticipy.ai response matches what we expect.
#
# Usage:
#   scripts/verify-deploy.sh <path> <expected-pattern> [wait-seconds]
#
# Example:
#   scripts/verify-deploy.sh /api/app/state '"engine":{"status":"ready"' 90
#   scripts/verify-deploy.sh /install.sh '^echo "Done\. Anticipy is installed' 90
#   scripts/verify-deploy.sh /flash 'Connect your pendant' 120
#
# Behavior:
#   1. Pushes the current branch to main (fails if not on main).
#   2. Captures the new commit hash.
#   3. Polls the live URL until the pattern matches OR the timeout expires.
#   4. Prints commit hash, push output, final curl response, verdict.
#
# Exits 0 on verified, 1 on failure. Honors the "two honest attempts" rule by
# polling rather than single-shot, but does NOT retry after a hard timeout —
# it prints the failing state and exits so the caller can investigate.

set -euo pipefail

PATH_TO_CHECK="${1:?missing path arg, e.g. /api/app/state}"
PATTERN="${2:?missing pattern arg, e.g. \"engine.*ready\"}"
WAIT_TIMEOUT_S="${3:-180}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

BRANCH="$(git symbolic-ref --short HEAD)"
if [ "$BRANCH" != "main" ]; then
  echo "FAIL: must be on main, currently on $BRANCH" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "WARNING: working tree is dirty; pushing only what is committed" >&2
fi

PUSH_OUTPUT="$(git push origin main 2>&1 || true)"
COMMIT_HASH="$(git rev-parse HEAD)"
COMMIT_SHORT="$(git rev-parse --short HEAD)"

echo "commit=$COMMIT_SHORT"
echo "push_output:"
echo "$PUSH_OUTPUT"
echo

LIVE_URL="https://www.anticipy.ai${PATH_TO_CHECK}"
echo "polling $LIVE_URL for pattern: $PATTERN"
echo "timeout: ${WAIT_TIMEOUT_S}s"
echo

START_TS=$(date +%s)
ATTEMPT=0
LAST_BODY=""
LAST_CODE=""

while true; do
  ATTEMPT=$((ATTEMPT + 1))
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TS))

  RESPONSE_FILE=$(mktemp)
  LAST_CODE=$(curl -sS -o "$RESPONSE_FILE" -w '%{http_code}' "$LIVE_URL" || echo "000")
  LAST_BODY=$(cat "$RESPONSE_FILE")
  rm -f "$RESPONSE_FILE"

  if [ "$LAST_CODE" = "200" ] && echo "$LAST_BODY" | grep -qE "$PATTERN"; then
    echo "DEPLOY VERIFIED $COMMIT_SHORT (elapsed ${ELAPSED}s, attempt $ATTEMPT)"
    echo
    echo "response:"
    echo "$LAST_BODY"
    exit 0
  fi

  if [ "$ELAPSED" -ge "$WAIT_TIMEOUT_S" ]; then
    echo "DEPLOY FAILED $COMMIT_SHORT (elapsed ${ELAPSED}s, ${ATTEMPT} attempts)" >&2
    echo "last_http_code=$LAST_CODE" >&2
    echo "last_response (truncated 2KB):" >&2
    echo "$LAST_BODY" | head -c 2000 >&2
    echo >&2
    exit 1
  fi

  sleep 5
done
