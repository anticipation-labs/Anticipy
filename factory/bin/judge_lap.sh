#!/usr/bin/env bash
# One fresh adversarial judge session. Usage: judge_lap.sh <LAP> [--self-check]
# Writes logs/factory/laps/<LAP>/verdict.md (+ judge.json) or <LAP>_selfcheck.md.
# FACTORY_JUDGE_CMD overrides the claude invocation (smoke tests).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
LAP="${1:?lap id}"
MODE="${2:-}"
LAPDIR="logs/factory/laps/$LAP"
mkdir -p "$LAPDIR"
source factory/config/factory.conf

if [[ "$MODE" == "--self-check" ]]; then
  PROMPT_FILE="factory/prompts/JUDGE_SELFCHECK.md"
  OUT="$LAPDIR/selfcheck.md"
else
  PROMPT_FILE="factory/prompts/JUDGE.md"
  OUT="$LAPDIR/verdict.md"
fi

HEADER="LAP=$LAP
LAPDIR=$LAPDIR
You are one bounded JUDGE session of the Anticipy Factory. You are NOT the builder.
Write your verdict to $OUT and a one-line JSON summary {\"verdict\": ...} to $LAPDIR/judge.json."

PROMPT="$HEADER

$(cat "$PROMPT_FILE")"

STREAM="$LAPDIR/judge.stream.jsonl"

if [[ -n "${FACTORY_JUDGE_CMD:-}" ]]; then
  bash -c "$FACTORY_JUDGE_CMD" > "$STREAM" 2>&1
  exit $?
fi

MODEL_ARGS=()
[[ -n "${JUDGE_MODEL:-}" ]] && MODEL_ARGS+=(--model "$JUDGE_MODEL")
CLAUDE="${CLAUDE_BIN:-claude}"

"$CLAUDE" -p "$PROMPT" \
  --dangerously-skip-permissions \
  --output-format stream-json --verbose \
  ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
  > "$STREAM" 2> "$LAPDIR/judge.err" &
CPID=$!
(
  sleep "${JUDGE_WALL_CAP_SECONDS:-1200}"
  pkill -P "$CPID" 2>/dev/null; kill "$CPID" 2>/dev/null
) & WATCHDOG=$!
wait "$CPID"; rc=$?
kill "$WATCHDOG" 2>/dev/null
wait "$WATCHDOG" 2>/dev/null
pkill -P "$CPID" 2>/dev/null || true
exit $rc
