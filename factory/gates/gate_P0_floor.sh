#!/usr/bin/env bash
# P0 floor gate: the Factory's own machinery works end to end.
# 1) scorer selftest passes  2) persona runner boots 2 personas in mock mode and
# produces scoreable output  3) scoreboard dry-run writes a valid row
# 4) spend parser reads a canned claude cost envelope.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
PY="engine/.venv/bin/python"
LAP="${1:-gate-p0-$(date -u +%H%M%S)}"
TMP="logs/factory/runs/$LAP-floor"

echo "[gate_P0] 1/4 scorer selftest"
"$PY" factory/bin/persona_score.py --selftest >/dev/null || { echo "FAIL: scorer selftest"; exit 1; }

echo "[gate_P0] 2/4 persona runner (2 personas, stub tier)"
"$PY" factory/bin/persona_run.py --bank factory/personas/dev \
  --personas parent_dana,student_kayla --lap "$LAP-floor" --tier stub \
  --out "$TMP" >/dev/null || { echo "FAIL: persona runner"; exit 1; }
"$PY" factory/bin/persona_score.py --runs "$TMP" --bank factory/personas/dev \
  --out "$TMP/metrics.json" >/dev/null || { echo "FAIL: scoring the run"; exit 1; }
"$PY" - "$TMP/metrics.json" <<'EOF' || { echo "FAIL: metrics incomplete"; exit 1; }
import json, sys
m = json.load(open(sys.argv[1]))
agg = m["aggregate"]
required = ["catch_rate_worst", "false_action_count", "silent_harm_count", "interrupt_cost"]
missing = [k for k in required if k not in agg]
assert not missing, f"missing {missing}"
assert agg["personas_run"] == 2, f"expected 2 personas, got {agg['personas_run']}"
EOF

echo "[gate_P0] 3/4 scoreboard dry-run"
mkdir -p "logs/factory/laps/$LAP"
cp "$TMP/metrics.json" "logs/factory/laps/$LAP/metrics.json"
echo '{"lap_type":"groundwork","intended_metric":"catch_rate_worst","hypothesis":"gate self-test"}' \
  > "logs/factory/laps/$LAP/manifest.json"
echo '{"all_scans_passed": true, "phase_gate_passed": false, "builder_commit": "'"$(git rev-parse HEAD)"'", "wall_seconds": 0, "budget_mode": "FULL", "spend_total_usd": 0.0}' \
  > "logs/factory/laps/$LAP/gate_results.json"
"$PY" factory/bin/scoreboard.py --lap "$LAP" --dry-run >/dev/null || { echo "FAIL: scoreboard dry-run"; exit 1; }

echo "[gate_P0] 4/4 spend parser"
printf '{"type":"result","total_cost_usd":1.23,"num_turns":4}\n' > "logs/factory/laps/$LAP/canned.json"
COST=$("$PY" -c "
import sys; sys.path.insert(0, 'factory/bin')
import importlib.util
spec = importlib.util.spec_from_file_location('spend', 'factory/bin/spend.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.cost_from('logs/factory/laps/$LAP/canned.json'))")
[[ "$COST" == "1.23" ]] || { echo "FAIL: spend parser got $COST"; exit 1; }

echo "[gate_P0] PASS — Factory floor is solid"
exit 0
