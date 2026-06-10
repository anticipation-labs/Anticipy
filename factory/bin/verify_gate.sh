#!/usr/bin/env bash
# Mechanical verdict for one lap: scans + regression suite + persona evals + phase gate.
# Usage: verify_gate.sh <LAP> <BASE_COMMIT>
# Writes logs/factory/laps/<LAP>/gate_results.json and metrics.json. Exit 0 = lap keepable.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
LAP="${1:?lap id}"
BASE="${2:?base commit}"
LAPDIR="logs/factory/laps/$LAP"
mkdir -p "$LAPDIR"
PY="engine/.venv/bin/python"
START=$(date +%s)

target_get() { grep -E "^$1:" factory/TARGET.md | head -1 | sed "s/^$1:[[:space:]]*//"; }
PHASE_GATE="$(target_get phase_gate)"
EVAL_TIER="$(target_get eval_tier)"; EVAL_TIER="${EVAL_TIER:-stub}"

fail=0

# ---- 1. scans ----
SCANS_JSON=$(bash factory/bin/scans.sh "$BASE" "$LAP") || fail=1
echo "$SCANS_JSON" > "$LAPDIR/scans.json"

# ---- 2. regression suite (stub/mock, free) ----
if bash scripts/run_suite.sh > "$LAPDIR/suite.out" 2>&1; then
  SUITE=PASS
else
  SUITE=FAIL; fail=1
fi

# ---- 3. persona evals -> metrics.json ----
if "$PY" factory/bin/persona_run.py --bank factory/personas/dev --lap "$LAP" \
     --tier "$EVAL_TIER" > "$LAPDIR/persona_run.out" 2>&1; then
  RUN=PASS
else
  RUN=FAIL; fail=1
fi
if "$PY" factory/bin/persona_score.py --runs "logs/factory/runs/$LAP" \
     --bank factory/personas/dev --out "$LAPDIR/metrics.json" > /dev/null 2> "$LAPDIR/score.err"; then
  SCORE=PASS
else
  SCORE=EVAL_BROKEN; fail=1
fi

# ---- 4. hard guards from metrics ----
GUARDS=PASS
if [[ -f "$LAPDIR/metrics.json" ]]; then
  HARM=$("$PY" -c "import json;print(json.load(open('$LAPDIR/metrics.json'))['aggregate'].get('silent_harm_count',0))" 2>/dev/null || echo 99)
  if [[ "$HARM" != "0" ]]; then GUARDS="FAIL: silent_harm_count=$HARM"; fail=1; fi
fi

# ---- 5. phase gate — ONLY when the builder requests a closure attempt (manifest
#         attempt_gate_close=true) or the foreman forces it. Live-side-effect gates
#         (real calendar/SMS) must not run on every lap (ledger B1). ----
PHASE_GATE_PASSED=false
ATTEMPT=$("$PY" -c "import json;print(json.dumps(json.load(open('$LAPDIR/manifest.json')).get('attempt_gate_close', False)))" 2>/dev/null || echo false)
if [[ "$ATTEMPT" == "true" || "${FACTORY_FORCE_GATE:-0}" == "1" ]]; then
  if [[ -n "$PHASE_GATE" && -f "$PHASE_GATE" ]]; then
    if bash "$PHASE_GATE" "$LAP" > "$LAPDIR/phase_gate.out" 2>&1; then PHASE_GATE_PASSED=true; fi
  fi
else
  echo "phase gate not attempted (manifest attempt_gate_close not set)" > "$LAPDIR/phase_gate.out"
fi

WALL=$(( $(date +%s) - START ))
BUILDER_COMMIT=$(git rev-parse HEAD)
ALL_SCANS=$([[ $fail -eq 0 ]] && echo true || echo false)

"$PY" - "$LAPDIR" <<EOF
import json, sys
lapdir = sys.argv[1]
scans = json.load(open(f"{lapdir}/scans.json"))
out = {
  "scans": scans,
  "suite": "$SUITE",
  "persona_run": "$RUN",
  "persona_score": "$SCORE",
  "guards": "$GUARDS",
  "phase_gate": "$PHASE_GATE",
  "phase_gate_passed": $([[ "$PHASE_GATE_PASSED" == "true" ]] && echo True || echo False),
  "all_scans_passed": $([[ "$ALL_SCANS" == "true" ]] && echo True || echo False),
  "builder_commit": "$BUILDER_COMMIT",
  "wall_seconds": $WALL,
  "budget_mode": "${FACTORY_BUDGET_MODE:-FULL}",
  "spend_total_usd": 0.0,
}
json.dump(out, open(f"{lapdir}/gate_results.json", "w"), indent=2, sort_keys=True)
print(json.dumps(out, indent=2, sort_keys=True))
EOF

exit $fail
