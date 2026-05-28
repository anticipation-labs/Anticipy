#!/usr/bin/env bash
# journey.sh — verify all 7 steps of docs/JOURNEY.md against real artifacts
#
# Tiered verification (per BOOTSTRAP.md Rule 2):
#   Tier 0: HTTP/Supabase/file existence/process checks (deterministic)
#   Tier 1: DOM/AX-tree queries via Playwright or AXUIElement (deterministic)
#   Tier 2: OpenCV baseline correlation against verifier/baselines/ (deterministic)
#   Tier 3: LLM-based last resort, only when tiers 0-2 cannot answer
#
# Exit 0 only if all 7 steps pass. Exit non-zero with the failing step number.

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"

source scripts/load_env.sh
load_anticipy_env

DRY=0
for arg in "$@"; do
  [ "$arg" = "--dry-run" ] && DRY=1
done

PY="python3"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="state/journey-runs/$RUN_ID"
mkdir -p "$RUN_DIR"

log() { echo "[journey $RUN_ID] $*"; }

run_step() {
  local n="$1"
  local desc="$2"
  local script="$3"

  log "Step $n start: $desc"

  if [ "$DRY" = "1" ]; then
    $PY "$script" --dry-run --run-dir "$RUN_DIR" > "$RUN_DIR/step_$n.log" 2>&1 || {
      log "Step $n DRY result captured."
      return 0
    }
    log "Step $n DRY ok."
    return 0
  fi

  $PY "$script" --run-dir "$RUN_DIR" > "$RUN_DIR/step_$n.log" 2>&1 || {
    local rc=$?
    log "Step $n FAILED (exit $rc). See $RUN_DIR/step_$n.log"
    echo "$n" > "$RUN_DIR/failed_step.txt"
    return $rc
  }
  log "Step $n PASSED."
}

# Each step's verifier is a separate Python file. Easier to maintain, easier to swap models per step.
run_step 1 "Web front door" verifier/steps/step1_front_door.py
run_step 2 "Signup" verifier/steps/step2_signup.py
run_step 3 "Download" verifier/steps/step3_download.py
run_step 4 "Install and launch" verifier/steps/step4_install_launch.py
run_step 5 "Onboarding dossier" verifier/steps/step5_onboarding.py
run_step 6 "Input pipeline" verifier/steps/step6_input.py
run_step 7 "Action execution" verifier/steps/step7_action.py

log "All 7 steps passed."
echo "0" > "$RUN_DIR/failed_step.txt"
exit 0
