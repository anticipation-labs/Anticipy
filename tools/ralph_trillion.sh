#!/usr/bin/env bash
# Ralph Trillion Loop. One iteration: check gates, dispatch one headless claude
# remediation on the highest-leverage missing item. Supervisor wraps in while.
set -u
REPO="${REPO:-/Users/omarebrahim/Developer/Anticipy-V7}"
cd "$REPO"
LOG_DIR="state/v7/supervisor"
LOG="$LOG_DIR/ralph_trillion.log"
RUN_DIR="state/v7/ralph_trillion_runs"
mkdir -p "$LOG_DIR" "$RUN_DIR"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[ralph_trillion $(ts)] $*" | tee -a "$LOG"; }

bash scripts/v7/trillion_dollar_check.sh > /tmp/trillion_check.log 2>&1
status_rc=$?

if [ "$status_rc" -eq 0 ]; then
  log "TRILLION_DOLLAR_MET. Writing DONE.md.trillion."
  cat > tasks/DONE.md.trillion <<EOF
# DONE: trillion-dollar criteria met
ts: $(ts)
local_head: $(git rev-parse HEAD)
See state/v7/trillion_dollar_status.json for the 7 criteria.
EOF
  exit 0
fi

missing_json="$(jq -c '.missing' state/v7/trillion_dollar_status.json 2>/dev/null || echo '[]')"
log "missing: $missing_json"

priority=""
for cand in deploy_parity gates z001 precision bridge_load m3_sync verb_categories; do
  if echo "$missing_json" | jq -e --arg c "$cand" '.[] | select(startswith($c))' >/dev/null 2>&1; then
    priority="$cand"; break
  fi
done
[ -z "$priority" ] && priority="$(echo "$missing_json" | jq -r '.[0] // "unknown"' | cut -d: -f1)"
log "priority=$priority"

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
THIS_RUN="$RUN_DIR/$RUN_TS-$priority"
mkdir -p "$THIS_RUN"

case "$priority" in
  deploy_parity) prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Source /Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local. Deploy parity red. Pull origin/main fresh. Update state/builds/manifest.json latest_commit to current HEAD. Push. Wait Vercel up to 5 min. Verify https://www.anticipy.ai/api/app/state commit matches local HEAD. No frozen edits. No em-dashes. Under 200 words." ;;
  gates) red="$(echo "$missing_json" | jq -r '.[] | select(startswith(\"gates\")) | sub(\"^gates:\"; \"\")')"; prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Red gates: $red. Read scripts/v7/check_done.sh. Pick ONE red gate, fix it against the live engine on 8731 without restart. Commit + push. Report which gate fixed. Under 200 words." ;;
  z001) prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Z-001 below 9/9. Read latest state/v7/z001_e2e_runs/*/result.json. Fix the failing step. Most likely gmail_draft_visible needs CDP Input.insertText into compose body after Page.navigate. Run scripts/v7/z001_e2e_harness.py. Commit + push. Under 250 words." ;;
  precision) prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Memory precision below 0.75. Read latest state/v7/memory_precision_*.json. The clarify-reflex fix shipped to source (9c247002). Re-run scripts/v7/e2e_hard_transcripts.sh + scripts/v7/score_memory_precision.py against the live engine. Commit + push. Under 250 words." ;;
  bridge_load) prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Bridge load below 40/50. Re-run scripts/v7/bridge_load_test.py. If still bad, verify ~/.anticipy/anticipy_bridge_fallback.py matches scripts/v7/anticipy_bridge_fallback_cdp.py (async-rewrite from W5b). Redeploy if not. Commit if changes. Under 200 words." ;;
  m3_sync) prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. M3 Supabase round trip failed. Re-run scripts/v7/verify_m3_cloud_sync.py against latest engine. M3 fix landed at de1a8c38. If sync still broken, document next gap. Use Supabase MCP tools. Commit + push. Under 250 words." ;;
  verb_categories) prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. verb_category_count below 20. Run 1-2 strangers in new verb categories: accommodation_booking, ride_share_request, subscription_management, flight_check, restaurant_booking. Real screenshots + evaluator pass required. Bridge 7777 + background tabs only. Commit + push. Under 250 words." ;;
  *) prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Trillion-dollar criterion '$priority' missing. Read state/v7/trillion_dollar_status.json. Investigate, fix, verify. Commit + push. Under 250 words." ;;
esac

log "dispatching claude headless"
TIMEOUT_BIN="$(command -v gtimeout || command -v timeout || true)"
RUN_OUT="$THIS_RUN/agent_output.log"
RUN_RC=0
if [ -n "$TIMEOUT_BIN" ]; then
  "$TIMEOUT_BIN" 1800 claude --print --permission-mode bypassPermissions "$prompt" > "$RUN_OUT" 2>&1 || RUN_RC=$?
else
  claude --print --permission-mode bypassPermissions "$prompt" > "$RUN_OUT" 2>&1 || RUN_RC=$?
fi
log "claude rc=$RUN_RC"
bash scripts/v7/trillion_dollar_check.sh >> "$RUN_OUT" 2>&1
log "recheck rc=$?"
exit 0
