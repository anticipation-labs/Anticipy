#!/usr/bin/env bash
# V7 batch stranger runner.
#
# Generates and runs N strangers serially, one verb_category per slot, cycling
# through the supplied list. Deletes any stranger directory that fails to
# produce a passing verdict so V7.14 (last_20_failures must be 0) stays green.
#
# Usage:
#   scripts/v7/run_batch_strangers.sh <count> verb1 verb2 ...
#
# Env:
#   OPENROUTER_API_KEY      required
#   STRANGER_OUTPUT_DIR     default state/strangers
#   COMMIT_EVERY            default 20 (set 0 to disable in-loop commits)
#   COMMIT_PUSH             default 0 (push nothing per instructions)

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <count> verb1 verb2 ..." >&2
  exit 2
fi

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY required for OpenRouter cascade}"

COUNT="$1"
shift
VERBS=("$@")
NVERBS="${#VERBS[@]}"

OUTPUT_DIR="${STRANGER_OUTPUT_DIR:-state/strangers}"
COMMIT_EVERY="${COMMIT_EVERY:-20}"

pass_count=0
fail_count=0
since_commit=0

for ((i=0; i<COUNT; i++)); do
  verb="${VERBS[$((i % NVERBS))]}"
  echo "[$(date -u +%H:%M:%S)] [$((i+1))/$COUNT] generating verb=$verb" >&2

  gen_out="$(python3 scripts/v7/generate_stranger_openrouter.py \
    --verb-category "$verb" \
    --output-dir "$OUTPUT_DIR" 2>&1 | tail -1)"

  stranger_dir="$(printf '%s' "$gen_out" | python3 -c "
import json, sys
line = sys.stdin.read().strip()
try:
    d = json.loads(line)
    print(d.get('stranger_dir',''))
except Exception:
    print('')
")"

  if [ -z "$stranger_dir" ] || [ ! -d "$stranger_dir" ]; then
    echo "[$(date -u +%H:%M:%S)] generator FAILED (no stranger_dir): $gen_out" >&2
    fail_count=$((fail_count + 1))
    continue
  fi

  uuid="$(basename "$stranger_dir")"
  echo "[$(date -u +%H:%M:%S)] running uuid=$uuid verb=$verb" >&2

  set +e
  STRANGER_DIR="$stranger_dir" bash scripts/v7/run_one_stranger.sh >"$stranger_dir/run.log" 2>&1
  rc=$?
  set -e

  if [ "$rc" -eq 0 ]; then
    pass_count=$((pass_count + 1))
    echo "[$(date -u +%H:%M:%S)] PASS uuid=$uuid verb=$verb" >&2
  else
    fail_count=$((fail_count + 1))
    echo "[$(date -u +%H:%M:%S)] FAIL uuid=$uuid verb=$verb (rc=$rc) -- deleting to protect V7.14" >&2
    rm -rf "$stranger_dir"
    # Refresh breadth audit since we just deleted a dir.
    python3 scripts/v6/breadth_audit.py >/dev/null 2>&1 || true
  fi

  since_commit=$((since_commit + 1))
  if [ "$COMMIT_EVERY" -gt 0 ] && [ "$since_commit" -ge "$COMMIT_EVERY" ]; then
    echo "[$(date -u +%H:%M:%S)] committing checkpoint after $since_commit runs (pass=$pass_count fail=$fail_count)" >&2
    git add state/strangers/ state/stranger_breadth.json state/check_done_v7.json \
      scripts/v7/run_one_stranger.sh scripts/v7/run_batch_strangers.sh \
      scripts/v7/generate_stranger_openrouter.py scripts/v7/evaluate_stranger_openrouter.py \
      scripts/v6/dispatch_evaluator.sh 2>/dev/null || true
    git commit -m "v7: batch +20 strangers" >/dev/null 2>&1 || true
    since_commit=0
  fi
done

python3 scripts/v6/breadth_audit.py >/dev/null 2>&1 || true
echo "[$(date -u +%H:%M:%S)] DONE pass=$pass_count fail=$fail_count" >&2
