#!/usr/bin/env bash
# Regression pin for the /download front-door button.
#
# The /download page's "Download for macOS" button points at
# /api/download/anticipy-execute. That route used to be MISSING -> a 404 dead
# button. This test boots the Next app and proves:
#   - GET /api/download/anticipy-execute is NOT a 404 (the bug);
#   - with the committed dev bundle present, it returns 200 + a real .zip
#     (application/zip, attachment) carrying the unsigned developer preview;
#   - the honest "developer-preview" provenance header is set (never "signed").
#
# No Apple signing/notarization happens here (Omar-gated); no fake binary.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${ANTICIPY_TEST_DOWNLOAD_PORT:-3196}"
BASE="http://127.0.0.1:${PORT}"
HDR="$(mktemp -t anticipy-dl-hdr-XXXXXX)"
BODY="$(mktemp -t anticipy-dl-body-XXXXXX)"
LOG="$(mktemp -t anticipy-dl-next-XXXXXX.log)"
PID=""

cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  rm -f "$HDR" "$BODY" "$LOG"
}
trap cleanup EXIT

cd "$REPO"
# Public download front door: no owner token configured (mirrors a public deploy).
npm run dev -- --hostname 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
PID="$!"

ready=0
for _ in $(seq 1 120); do
  if curl -fsS "$BASE/download" -o /dev/null 2>/dev/null; then
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

# The download page itself must render.
code="$(curl -sS -o /dev/null -w "%{http_code}" "$BASE/download")"
test "$code" = "200" || { echo "FAIL: /download did not render (got $code)"; exit 1; }

# The button target must NOT 404 (the regression).
code="$(curl -sS -D "$HDR" -o "$BODY" -w "%{http_code}" "$BASE/api/download/anticipy-execute")"
if [ "$code" = "404" ]; then
  echo "FAIL: /api/download/anticipy-execute returned 404 (dead Download button)"
  exit 1
fi
test "$code" = "200" || { echo "FAIL: expected 200 from download route, got $code"; exit 1; }

# Provenance header is always present and honest (never claims "signed").
grep -qi '^x-anticipy-build:' "$HDR" || { echo "FAIL: missing x-anticipy-build provenance header"; cat "$HDR"; exit 1; }
if grep -qi '^x-anticipy-build: *signed' "$HDR"; then
  echo "FAIL: route must never claim a signed build"
  exit 1
fi

if [ -d "$REPO/macapp/dist/Anticipy.app" ] && [ -f "$REPO/macapp/dist/Anticipy.app/Contents/MacOS/Anticipy" ]; then
  # Bundle present -> must be a real zip attachment of the unsigned dev preview.
  grep -qi '^content-type: *application/zip' "$HDR" || { echo "FAIL: expected application/zip"; cat "$HDR"; exit 1; }
  grep -qi '^content-disposition:.*attachment' "$HDR" || { echo "FAIL: expected attachment disposition"; cat "$HDR"; exit 1; }
  grep -qi '^x-anticipy-build: *developer-preview-unsigned' "$HDR" || { echo "FAIL: bundle response must be marked developer-preview-unsigned"; cat "$HDR"; exit 1; }
  # The bytes must be a valid zip carrying the .app executable (real artifact, not a stub).
  unzip -l "$BODY" >/tmp/anticipy_dl_listing.txt 2>/dev/null || { echo "FAIL: served bytes are not a valid zip"; exit 1; }
  grep -q 'Anticipy.app/Contents/MacOS/Anticipy' /tmp/anticipy_dl_listing.txt || { echo "FAIL: zip missing the app executable"; cat /tmp/anticipy_dl_listing.txt; exit 1; }
  echo "PASS download_route: /api/download/anticipy-execute serves the real unsigned dev .app.zip (no 404, no fake binary)"
else
  # No bundle built -> honest 200, rendered as a PREMIUM HTML page (charcoal/cream/DM Serif),
  # never a 404, never a fake binary, and never dev-console noise (no bash, no ports, no
  # "developer preview" jargon). The message stays in Donna's voice and gives a human a way
  # to reach a human.
  grep -qi '^content-type: *text/html' "$HDR" || { echo "FAIL: expected text/html premium fallback"; cat "$HDR"; exit 1; }
  grep -qi 'almost ready\|on the way' "$BODY" || { echo "FAIL: fallback must say it's coming, in human copy"; cat "$BODY"; exit 1; }
  if grep -qiE 'bash |:8787|:3000|build_app\.sh|developer preview' "$BODY"; then
    echo "FAIL: fallback leaked dev-console noise (bash/ports/jargon) to a real user"; cat "$BODY"; exit 1
  fi
  echo "PASS download_route: /api/download/anticipy-execute returns premium HTML preview notice (no bundle; no 404; no jargon)"
fi
