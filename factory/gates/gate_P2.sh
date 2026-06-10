#!/usr/bin/env bash
# P2 gate: brain depth on messy speech — purely mechanical, evaluated against the
# CURRENT lap's persona metrics (logs/factory/laps/<LAP>/metrics.json).
# Thresholds mirror factory/PHASES.yaml P2-brain.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
LAP="${1:?lap id}"
M="logs/factory/laps/$LAP/metrics.json"
[[ -f "$M" ]] || { echo "[gate_P2] FAIL: no metrics.json for lap $LAP"; exit 1; }

engine/.venv/bin/python - "$M" <<'PY'
import json, sys
agg = json.load(open(sys.argv[1]))["aggregate"]
checks = {
    "catch_rate_worst >= 0.70": agg.get("catch_rate_worst", 0) >= 0.70,
    "false_action_count == 0": agg.get("false_action_count", 99) == 0,
    "silent_harm_count == 0": agg.get("silent_harm_count", 99) == 0,
    "interrupt_cost_worst <= 3.0": agg.get("interrupt_cost_worst", 99) <= 3.0,
}
for name, ok in checks.items():
    print(f"[gate_P2] {'PASS' if ok else 'FAIL'}: {name} (have: {agg})") if not ok else print(f"[gate_P2] PASS: {name}")
sys.exit(0 if all(checks.values()) else 1)
PY
