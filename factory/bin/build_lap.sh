#!/usr/bin/env bash
# One fresh, bounded builder session. Usage: build_lap.sh <LAP> <TIER:FULL|FREE>
# FACTORY_BUILD_CMD overrides the claude invocation (used by smoke tests).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
LAP="${1:?lap id}"
TIER="${2:-FULL}"
LAPDIR="logs/factory/laps/$LAP"
mkdir -p "$LAPDIR"
source factory/config/factory.conf

PER_LAP_USD=$(engine/.venv/bin/python -c "import json;print(json.load(open('factory/config/budget.json'))['per_lap_build_usd'])")

HEADER="LAP=$LAP
TIER=$TIER
PHASE=$(grep -E '^current_phase:' factory/TARGET.md | sed 's/^current_phase:[[:space:]]*//')
You are one bounded builder lap of the Anticipy Factory. Everything you need to know is in the instructions below and on disk. Work, commit, stop."

PROMPT="$HEADER

$(cat factory/prompts/BUILD.md)"

STREAM="$LAPDIR/build.stream.jsonl"

if [[ -n "${FACTORY_BUILD_CMD:-}" ]]; then
  # test hook: run the override instead of a real model session
  bash -c "$FACTORY_BUILD_CMD" > "$STREAM" 2>&1
  rc=$?
  echo "{\"type\":\"result\",\"total_cost_usd\":0.0,\"smoke\":true}" >> "$STREAM"
  exit $rc
fi

MODEL_ARGS=()
[[ -n "${BUILD_MODEL:-}" ]] && MODEL_ARGS+=(--model "$BUILD_MODEL")
CLAUDE="${CLAUDE_BIN:-claude}"

# run claude in background so the watchdog can kill the exact PID + its subtree (ledger D3)
"$CLAUDE" -p "$PROMPT" \
  --dangerously-skip-permissions \
  --output-format stream-json --verbose \
  ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
  > "$STREAM" 2> "$LAPDIR/build.err" &
CPID=$!
(
  sleep "${BUILD_WALL_CAP_SECONDS:-2400}"
  pkill -P "$CPID" 2>/dev/null; kill "$CPID" 2>/dev/null
) & WATCHDOG=$!
wait "$CPID"; rc=$?
kill "$WATCHDOG" 2>/dev/null
wait "$WATCHDOG" 2>/dev/null
pkill -P "$CPID" 2>/dev/null || true

# extract the final result envelope for spend tracking
engine/.venv/bin/python - "$STREAM" "$LAPDIR/build.json" <<'PY'
import json, sys
stream, out = sys.argv[1], sys.argv[2]
result = {}
try:
    with open(stream) as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") == "result" or "total_cost_usd" in obj:
                result = obj
except FileNotFoundError:
    pass
json.dump(result, open(out, "w"), indent=2)
PY
exit $rc
