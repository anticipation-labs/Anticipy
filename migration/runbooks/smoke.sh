#!/usr/bin/env bash
# smoke.sh — prove every page and every API route still answers.
#
# WHAT IT CHECKS
#   pages       every src/app/**/page.tsx  -> expect the status in EXPECT, else 200
#   API routes  every src/app/**/route.ts  -> expect NOT 5xx
#
# WHY IT IS SHAPED THIS WAY
#   The route list is DERIVED FROM THE FILESYSTEM at run time, not typed into
#   this file. A hand-maintained list silently stops covering a route the day
#   somebody adds one, and the gap is invisible exactly when it matters -- on
#   cutover day. Run it from the repo root so it can read src/app.
#
#   It NEVER sends POST/PUT/PATCH/DELETE. 46 of the 97 route.ts files export no
#   GET at all, and several of those charge a card, send mail, or write a row.
#   For those it sends OPTIONS and, failing that, GET: a 405 from a POST-only
#   route is PROOF THE ROUTE IS MOUNTED AND RUNNING, which is the entire claim
#   this script makes. It is deliberately not a functional test suite.
#
# USAGE
#   ./migration/runbooks/smoke.sh https://anticipy.ai
#   ./migration/runbooks/smoke.sh https://anticipy-site.<subdomain>.workers.dev
#   ./migration/runbooks/smoke.sh http://localhost:3000
#
#   --json out.json   also write a machine-readable result, for diffing two
#                     backends:  jq -s '.[0].results as $a | ...' prod.json cf.json
#   --gate-cookie V   the SIGNED value of the anticipy_internal_gate cookie, so
#                     the five /internal/* pages are exercised for real instead
#                     of scoring their 401. This is NOT the passcode: the cookie
#                     is "<exp>.<hmac>" (src/middleware.ts:26-38, name at :6).
#                     Get it by passing the gate in a browser and copying the
#                     cookie out of devtools. Expired values silently fail the
#                     check and you get 401s back, which look like a pass.
#   --quiet           only print failures and the summary
#
# EXIT
#   0  every check passed
#   1  at least one check failed
#   2  could not run (bad usage, missing curl, wrong directory)

set -uo pipefail

BASE=""
JSON_OUT=""
QUIET=0
GATE_COOKIE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --json)         JSON_OUT="${2:-}"; shift 2 ;;
    --gate-cookie)  GATE_COOKIE="${2:-}"; shift 2 ;;
    --quiet)        QUIET=1; shift ;;
    -h|--help)      sed -n '2,36p' "$0"; exit 0 ;;
    *)              BASE="${1%/}"; shift ;;
  esac
done

[ -n "$BASE" ] || { echo "usage: $0 <base-url> [--json out.json] [--gate-cookie V] [--quiet]" >&2; exit 2; }
command -v curl >/dev/null || { echo "smoke: curl not found" >&2; exit 2; }
[ -d src/app ] || { echo "smoke: run me from the repo root (no ./src/app here)" >&2; exit 2; }

# ---------------------------------------------------------------- expectations
#
# Every entry is a NON-200 that is correct behaviour, verified by following it.
# Sourced to the code that produces it so a reviewer can check the claim rather
# than trust the table.
#
#   /internal*      401  src/middleware.ts:149-176 -- passcode gate, body varies
#                        by Accept but the status is 401 either way
#   /engine*        301  src/middleware.ts:138-143 -> /app
#   /analytics      307  redirect to /analytics/login
#   /pre-orders     307  redirect to /pre-orders/purchase
#   /ugc /ugc/apply 307  next.config.mjs:42-43 -> anticipyfellowship.com
#   /fellowships*   307  next.config.mjs:53-56 -> anticipyfellowship.com
#
# NOTE these are the codes for -o /dev/null WITHOUT -L. The script does not
# follow redirects: a 301 that lands somewhere wrong is a different bug from a
# 301 that is not emitted, and collapsing them hides the first one.
expect_for() {
  case "$1" in
    # With a valid gate cookie these must be 200. Without one they must be 401.
    # Expecting 401 unconditionally would turn "the gate is broken and everyone
    # is locked out" into a passing run.
    /internal|/internal/*)            [ -n "$GATE_COOKIE" ] && echo 200 || echo 401 ;;
    /engine|/engine/*)                echo 301 ;;
    /analytics)                       echo 307 ;;
    /pre-orders)                      echo 307 ;;
    /ugc|/ugc/apply)                  echo 307 ;;
    /fellowships|/fellowships.html)   echo 307 ;;
    /fellowship-growth-learning*)     echo 307 ;;
    *)                                echo 200 ;;
  esac
}

# Dynamic segments need a concrete value or the request is meaningless. These
# are DELIBERATELY values that should not resolve to a real row: the claim is
# "the route is mounted and handles a miss", not "this id exists". A route that
# 404s a bogus id has passed; a route that 500s it has not.
sample_for_segment() {
  case "$1" in
    "[handle]")   echo "smoke-test-nobody" ;;
    "[intentId]") echo "00000000-0000-0000-0000-000000000000" ;;
    "[id]")       echo "smoke0000000000" ;;
    "[folder]")   echo "smoke-test-folder" ;;
    *)            echo "smoke-test" ;;
  esac
}

# fs path under src/app -> URL path.
#   (group)  route groups contribute nothing to the URL
#   @slot    parallel-route slots likewise
#   [x]      replaced by a sample above
to_url_path() {
  local rel="$1" out="" seg sample
  local IFS=/
  for seg in $rel; do
    [ -z "$seg" ] && continue
    case "$seg" in
      \(*\)) continue ;;
      @*)    continue ;;
      \[*\]) sample="$(sample_for_segment "$seg")"; out="$out/$sample" ;;
      *)     out="$out/$seg" ;;
    esac
  done
  [ -z "$out" ] && out="/"
  echo "$out"
}

# A 5xx that is the CORRECT answer. One entry, and it needs its citation with
# it: an allowlist nobody can audit is how a real 500 gets waved through six
# months later. Re-check this list on every run of the suite, not once.
#
#   /api/engine/deepgram-key  503  src/app/api/engine/deepgram-key/route.ts:6,24
#                                  "RETIRED 2026-05-13", retired_on in the body.
#                                  It answers 503 on purpose so callers switch
#                                  to the local engine. Deleting the route --
#                                  making it a 404 -- would be a behaviour
#                                  change, so it stays 503 and stays here.
expected_5xx() {
  case "$1" in
    /api/engine/deepgram-key) echo 503 ;;
    *)                        echo "" ;;
  esac
}

PASS=0; FAIL=0
FAILURES=""
JSON_ROWS=""

record() { # kind path method status expected verdict
  if [ -n "$JSON_OUT" ]; then
    JSON_ROWS="$JSON_ROWS{\"kind\":\"$1\",\"path\":\"$2\",\"method\":\"$3\",\"status\":$4,\"expected\":\"$5\",\"verdict\":\"$6\"},"
  fi
}

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }

CURL=(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 --retry 1 --retry-connrefused)
[ -n "$GATE_COOKIE" ] && CURL+=(--cookie "anticipy_internal_gate=$GATE_COOKIE")

probe() { # method url -> prints status (000 on transport failure)
  "${CURL[@]}" -X "$1" -H 'accept: text/html,application/json' "$2" 2>/dev/null || echo 000
}

say "smoke: $BASE"
say ""

# ------------------------------------------------------------------- 1. pages
say "--- pages ---"
PAGE_N=0
while IFS= read -r f; do
  rel="${f#src/app}"; rel="${rel%/page.tsx}"
  url="$(to_url_path "$rel")"
  exp="$(expect_for "$url")"
  code="$(probe GET "$BASE$url")"
  PAGE_N=$((PAGE_N+1))
  if [ "$code" = "$exp" ]; then
    PASS=$((PASS+1)); say "  ok    $code  $url"; record page "$url" GET "$code" "$exp" pass
  else
    FAIL=$((FAIL+1)); FAILURES="$FAILURES\n  PAGE  $url  got $code want $exp"
    printf '  FAIL  %s  %s (want %s)\n' "$code" "$url" "$exp"; record page "$url" GET "$code" "$exp" fail
  fi
done < <(find src/app -name page.tsx | sort)

# -------------------------------------------------------------- 2. API routes
say ""
say "--- api routes ---"
ROUTE_N=0
while IFS= read -r f; do
  rel="${f#src/app}"; rel="${rel%/route.ts}"
  url="$(to_url_path "$rel")"
  ROUTE_N=$((ROUTE_N+1))
  if grep -qE '^export (async )?function GET|^export const GET' "$f"; then
    method=GET
    code="$(probe GET "$BASE$url")"
  else
    # No GET export. OPTIONS first -- 24 of these export one explicitly for
    # CORS. If OPTIONS is not handled either, GET and accept the 405.
    method=OPTIONS
    code="$(probe OPTIONS "$BASE$url")"
    if [ "$code" = "000" ] || [ "$code" = "404" ]; then
      method=GET; code="$(probe GET "$BASE$url")"
    fi
  fi
  # The claim: mounted and not crashing. 5xx and transport failure fail;
  # 401/403/404/405/400 are the route answering.
  if [ "$code" = "000" ]; then
    FAIL=$((FAIL+1)); FAILURES="$FAILURES\n  ROUTE $url  no response ($method)"
    printf '  FAIL  ---  %s (%s, no response)\n' "$url" "$method"; record route "$url" "$method" 0 "non-5xx" fail
  elif [ "$code" -ge 500 ] && [ "$code" = "$(expected_5xx "$url")" ]; then
    PASS=$((PASS+1)); say "  ok    $code  $url ($method, 5xx by design)"
    record route "$url" "$method" "$code" "$code by design" pass
  elif [ "$code" -ge 500 ]; then
    FAIL=$((FAIL+1)); FAILURES="$FAILURES\n  ROUTE $url  got $code ($method)"
    printf '  FAIL  %s  %s (%s)\n' "$code" "$url" "$method"; record route "$url" "$method" "$code" "non-5xx" fail
  else
    PASS=$((PASS+1)); say "  ok    $code  $url ($method)"; record route "$url" "$method" "$code" "non-5xx" pass
  fi
done < <(find src/app -name route.ts | sort)

# ---------------------------------------------------------------- 3. summary
say ""
echo "================================================================"
echo "smoke  $BASE"
echo "  pages   $PAGE_N"
echo "  routes  $ROUTE_N"
echo "  pass    $PASS"
echo "  fail    $FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf 'failures:%b\n' "$FAILURES"
fi
echo "================================================================"

if [ -n "$JSON_OUT" ]; then
  printf '{"base":"%s","pages":%d,"routes":%d,"pass":%d,"fail":%d,"results":[%s]}\n' \
    "$BASE" "$PAGE_N" "$ROUTE_N" "$PASS" "$FAIL" "${JSON_ROWS%,}" > "$JSON_OUT"
  echo "wrote $JSON_OUT"
fi

[ "$FAIL" -eq 0 ]
