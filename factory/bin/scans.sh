#!/usr/bin/env bash
# All mechanical lap scans in one place. Usage: scans.sh <BASE_COMMIT> <LAP>
# Prints one JSON object; exits 0 only if every scan passed.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
BASE="${1:?base commit}"
LAP="${2:?lap id}"
LAPDIR="logs/factory/laps/$LAP"
mkdir -p "$LAPDIR"

fail=0
results="{"

note() { results="$results\"$1\": \"$2\", "; }

# ---- 1. forbidden paths: builder may not touch the control plane ----
FORBIDDEN='^(factory/|logs/factory/product_scoreboard.csv|logs/factory/RATCHET.json|logs/verdicts/|realdays/holdout/|scripts/realday.sh)'
touched=$(git diff --name-only "$BASE"..HEAD 2>/dev/null | grep -E "$FORBIDDEN" || true)
if [[ -n "$touched" ]]; then
  note forbidden_paths "FAIL: $(echo "$touched" | tr '\n' ' ')"
  fail=1
else
  note forbidden_paths PASS
fi

# ---- 2. owner literals in product code (added lines only) ----
LITERALS="factory/config/owner_literals.local.txt"
if [[ -f "$LITERALS" ]]; then
  hits=$(git diff "$BASE"..HEAD -- engine/ app/ extension/ macapp/ shared/ 2>/dev/null \
    | grep -E '^\+' | grep -ivE '^\+\+\+' | grep -iFf "$LITERALS" || true)
  if [[ -n "$hits" ]]; then
    h=$(echo "$hits" | shasum -a 256 | cut -c1-12)
    note owner_literals "FAIL: owner literal in product diff (hash $h)"
    fail=1
  else
    note owner_literals PASS
  fi
else
  note owner_literals "SKIPPED_NO_DENYLIST"
fi

# ---- 3. secret shapes in added lines ----
secrets=$(git diff "$BASE"..HEAD 2>/dev/null | grep -E '^\+' | grep -vE '^\+\+\+' \
  | grep -E '(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[bp]-|-----BEGIN [A-Z ]*PRIVATE KEY|AIza[0-9A-Za-z_\-]{30,})' || true)
if [[ -n "$secrets" ]]; then
  note secrets "FAIL: secret-shaped added line"
  fail=1
else
  note secrets PASS
fi

# ---- 4. holdout reads in the builder session stream ----
STREAM="$LAPDIR/build.stream.jsonl"
if [[ -f "$STREAM" ]]; then
  holdout=$(grep -E '(personas/holdout|realdays/holdout)' "$STREAM" || true)
  if [[ -n "$holdout" ]]; then
    note holdout_read "FAIL: builder touched holdout paths"
    fail=1
  else
    note holdout_read PASS
  fi
else
  note holdout_read "SKIPPED_NO_STREAM"
fi

# ---- 5. per-store recipe cap: no new retailer hostnames in agent code ----
recipe=$(git diff "$BASE"..HEAD -- engine/anticipy_engine/agent/ 2>/dev/null \
  | grep -E '^\+' | grep -vE '^\+\+\+' \
  | grep -E '"[a-z0-9\-]+\.(com|org|net)"|'"'"'[a-z0-9\-]+\.(com|org|net)'"'" || true)
if [[ -n "$recipe" ]]; then
  note recipe_cap "FAIL: new retailer hostname literal in agent/ (banned while TARGET bans recipes)"
  fail=1
else
  note recipe_cap PASS
fi

# ---- 6. working tree clean (no uncommitted leftovers) ----
if [[ -n "$(git status --porcelain 2>/dev/null | grep -vE '^\?\? (logs/|factory/\.lock|\.anticipy)' || true)" ]]; then
  note tree_clean "WARN: uncommitted tracked changes"
else
  note tree_clean PASS
fi

results="${results%, }}"
echo "$results"
exit $fail
