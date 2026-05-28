#!/usr/bin/env bash
# Drive strangers in a loop until V7.11 (100 successful interactions) is reached.
# Cycles a fixed verb list, replenishing breadth with each iteration.
#
# Usage:
#   OPENROUTER_API_KEY=... bash scripts/v7/run_until_100.sh [target_count]
#
# Env:
#   COMMIT_EVERY     default 20 (commit checkpoint after each N successes)
#   TARGET_COUNT     default 100 (V7.11 threshold)

set -euo pipefail

: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY required}"

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

TARGET="${1:-${TARGET_COUNT:-100}}"
COMMIT_EVERY="${COMMIT_EVERY:-20}"

# Rotation of verb categories. Heavy weight on the ones we know decline reliably.
VERBS=(
  email_draft_for_send_decline
  task_or_todo_add_ack
  notes_or_memo_create_act
  recipe_or_meal_plan_act
  health_or_workout_log_ack
  expense_or_budget_track_decline
  web_research_summarize_decline
  news_or_message_summary_decline
  file_search_or_open_decline
  phone_text_message_draft_decline
  code_or_terminal_run_decline
  asana_task_update_decline
  jira_issue_comment_decline
  airtable_record_edit_decline
  salesforce_lead_log_decline
  zendesk_ticket_comment_decline
  trello_card_move_decline
  calendar_event_create_clarify
  ambient_buried_intent
  canvas_design_edit_decline
  figma_design_edit_decline
  amazon_order_refund_decline
  shopify_admin_reply_decline
  purchase_lookup_decline
  travel_research_compare_decline
)
NVERBS="${#VERBS[@]}"

pass=0
fail=0
since_commit=0
iter=0
while :; do
  python3 scripts/v6/breadth_audit.py >/dev/null 2>&1 || true
  current="$(jq -r '.successful_interactions // 0' state/stranger_breadth.json 2>/dev/null || echo 0)"
  if [ "$current" -ge "$TARGET" ]; then
    echo "[$(date -u +%H:%M:%S)] reached target: $current >= $TARGET. stopping." >&2
    break
  fi

  verb="${VERBS[$((iter % NVERBS))]}"
  iter=$((iter + 1))
  echo "[$(date -u +%H:%M:%S)] iter=$iter current=$current verb=$verb" >&2

  gen_out="$(python3 scripts/v7/generate_stranger_openrouter.py \
    --verb-category "$verb" \
    --output-dir state/strangers 2>&1 | tail -1)"

  stranger_dir="$(printf '%s' "$gen_out" | python3 -c "
import json, sys
try:
    print(json.loads(sys.stdin.read().strip()).get('stranger_dir',''))
except Exception:
    print('')
")"

  if [ -z "$stranger_dir" ] || [ ! -d "$stranger_dir" ]; then
    echo "[$(date -u +%H:%M:%S)] generator FAILED for verb=$verb" >&2
    fail=$((fail + 1))
    continue
  fi

  uuid="$(basename "$stranger_dir")"
  set +e
  STRANGER_DIR="$stranger_dir" bash scripts/v7/run_one_stranger.sh >"$stranger_dir/run.log" 2>&1
  rc=$?
  set -e

  if [ "$rc" -eq 0 ]; then
    pass=$((pass + 1))
    since_commit=$((since_commit + 1))
    echo "[$(date -u +%H:%M:%S)] PASS uuid=$uuid verb=$verb (pass=$pass fail=$fail)" >&2
  else
    fail=$((fail + 1))
    echo "[$(date -u +%H:%M:%S)] FAIL uuid=$uuid verb=$verb rc=$rc -- deleting" >&2
    rm -rf "$stranger_dir"
    python3 scripts/v6/breadth_audit.py >/dev/null 2>&1 || true
  fi

  if [ "$COMMIT_EVERY" -gt 0 ] && [ "$since_commit" -ge "$COMMIT_EVERY" ]; then
    echo "[$(date -u +%H:%M:%S)] committing checkpoint" >&2
    git add state/strangers/ state/stranger_breadth.json state/check_done_v7.json \
      scripts/v7/ scripts/v6/dispatch_evaluator.sh 2>/dev/null || true
    git commit -m "v7: batch +20 strangers" >/dev/null 2>&1 || true
    since_commit=0
  fi
done

echo "[$(date -u +%H:%M:%S)] FINAL pass=$pass fail=$fail target=$TARGET" >&2
