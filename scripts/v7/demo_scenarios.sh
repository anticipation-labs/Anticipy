#!/bin/bash
# Real-world demo scenarios for the universal action loop.
#
# Drives Omar's real Chrome via /api/universal/run across at least 5
# real-world scenarios: Notion, Stripe, GitHub, Calendly, Gmail. The
# python script handles login probing, surface dispatch, screenshot
# capture, and per-scenario verdict.
#
# Aggregate verdict: PASS if at least 4 of 5 attempted scenarios end
# SUCCESS, FAIL otherwise. SKIPPED scenarios (not logged in) do not
# count toward either side.
#
# Output:
#   state/v7/demo_scenarios_runs/<ts>/aggregate.json
#   state/v7/demo_scenarios_runs/<ts>/<scenario_id>/result.json
#   state/v7/demo_scenarios_runs/<ts>/<scenario_id>/login_probe.png
#   state/v7/demo_scenarios_runs/<ts>/<scenario_id>/agent_window_after.png
#   state/v7/demo_scenarios_runs/<ts>/<scenario_id>/trajectory/*.png
#
# Exit codes:
#   0  aggregate PASS
#   1  aggregate FAIL
#   2  pre-flight failure (engine or bridge down)

set -uo pipefail
REPO="${REPO:-/Users/omarebrahim/Developer/Anticipy-V7}"
cd "$REPO"

PY_BIN="${PY_BIN:-python3}"
SCRIPT="$REPO/scripts/v7/demo_scenarios.py"

if [ ! -f "$SCRIPT" ]; then
  echo "[demo_scenarios.sh] FAIL: $SCRIPT not found" >&2
  exit 2
fi

ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

echo "[demo_scenarios.sh] starting at $(date -u +%FT%TZ)"
echo "[demo_scenarios.sh] engine = http://127.0.0.1:8731"
echo "[demo_scenarios.sh] bridge = http://127.0.0.1:7777"
echo "[demo_scenarios.sh] cdp    = http://localhost:9222"

# Forward any CLI args (e.g. --only notion_idea_capture,stripe_revenue_check).
"$PY_BIN" "$SCRIPT" "$@"
RC=$?

echo "[demo_scenarios.sh] finished at $(date -u +%FT%TZ) rc=$RC"
exit $RC
