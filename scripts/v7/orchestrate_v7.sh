#!/usr/bin/env bash
# V7 entrypoint. Keeps the existing mature orchestrator but anchors it to V7.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

require_anchor() {
  local file="$1"
  local needle="$2"
  if ! grep -q "$needle" "$file" 2>/dev/null; then
    echo "$file missing V7 loop-control anchor: $needle" >&2
    exit 3
  fi
}

require_anchor ANTICIPY_V7.md "public downloadable user-device engine"
require_anchor ANTICIPY_V7.md "SINGLE PRODUCT SPINE ORDER"
require_anchor ANTICIPY_V7.md "Verifier work may block fake receipts"
require_anchor roles/planner.md "installed public product path, unified input boundary"

export V7_MODE=1
export CONTRACT_FILE="${CONTRACT_FILE:-ANTICIPY_V7.md}"
export CHECK_DONE="${CHECK_DONE:-scripts/v7/check_done.sh}"
export V7_PRODUCT_SPINE_ORDER="${V7_PRODUCT_SPINE_ORDER:-installed_public_product_path,unified_input_boundary,surface_runtime_action_execution,memory_resolution,proactive_observation,breadth_clean_room}"
export V7_VERIFIER_ROLE="${V7_VERIFIER_ROLE:-guardrail_not_substitute}"
exec bash scripts/orchestrate_v6.sh "$@"
