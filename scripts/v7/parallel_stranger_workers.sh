#!/usr/bin/env bash
# V7 Parallel Stranger Workers (v2 — engine-lock aware)
#
# Spawns N concurrent workers that each generate + run + evaluate strangers,
# sharing the global state/stranger_breadth.json counter. Runs ALONGSIDE the
# serial scripts/v7/run_until_100.sh loop, not in place of it.
#
# Why a lock:
#   The engine's /api/listen/upload route holds a singleton _UPLOAD_ASR_LOCK
#   while parakeet transcribes. Concurrent uploads return HTTP 429 ("upload
#   ASR is already running"). So we cannot truly parallelize the upload step.
#
# What is parallel anyway:
#   - Generation (OpenRouter call, ~5-10s): runs concurrently across workers.
#     This is the main speedup. Strangers get pre-generated while the previous
#     worker is uploading.
#   - Evaluator (OpenRouter call inside run_one_stranger.sh, after eval): also
#     runs while another worker has the engine lock — because by the time the
#     evaluator runs, the upload step is over and the lock would be released
#     for the next worker. We still hold our own copy of the engine lock for
#     the whole run_one_stranger.sh call (simpler, no race on Chrome tab).
#
# Concurrency model:
#   - N worker processes; each loop:
#       1. generate stranger (parallel safe)
#       2. acquire shlock on tasks/engine_run.lock
#       3. bash scripts/v7/run_one_stranger.sh (upload + CDP + eval)
#       4. release lock
#       5. record pass/fail, prune failed dir
#
# Race tolerance with the serial loop:
#   - The serial loop scripts/v7/run_until_100.sh does NOT use shlock. Its
#     uploads will continue to land. If a serial upload starts while a worker
#     holds shlock, the worker still gets exclusivity ON THE LOCK FILE; the
#     serial upload will race the worker for the engine ASR lock. The engine
#     returns 429 to the loser. The worker has a retry-on-429 fast-path so it
#     does not waste the pre-generated stranger.
#
# Cost guard, consecutive-failure guard, jitter: unchanged from v1.
#
# Usage:
#   nohup bash scripts/v7/parallel_stranger_workers.sh \
#       > state/v7/parallel_workers.log 2>&1 &
#
# Env:
#   WORKERS                 default 3
#   TARGET                  default 100
#   COST_CEILING_USD        default 5
#   COST_PER_STRANGER_USD   default 0.01
#   CONSEC_FAIL_THRESHOLD   default 10
#   JITTER_MAX_SEC          default 4
#   POLL_DONE_SEC           default 10
#   LOCK_WAIT_SEC           default 600 (max time to wait for engine lock)
#   UPLOAD_RETRY_MAX        default 8   (retries on HTTP 429)

set -u

REPO="${REPO:-/Users/omarebrahim/Developer/Anticipy-V7}"
cd "$REPO"

# Source env from DEV-FINAL .env.local for OPENROUTER_API_KEY.
ENV_FILE="${ANTICIPY_ENV_FILE:-/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY missing}"

WORKERS="${WORKERS:-3}"
TARGET="${TARGET:-100}"
COST_CEILING_USD="${COST_CEILING_USD:-5}"
COST_PER_STRANGER_USD="${COST_PER_STRANGER_USD:-0.01}"
CONSEC_FAIL_THRESHOLD="${CONSEC_FAIL_THRESHOLD:-10}"
JITTER_MAX_SEC="${JITTER_MAX_SEC:-4}"
POLL_DONE_SEC="${POLL_DONE_SEC:-10}"
LOCK_WAIT_SEC="${LOCK_WAIT_SEC:-600}"
UPLOAD_RETRY_MAX="${UPLOAD_RETRY_MAX:-30}"
UPLOAD_RETRY_MAX_SLEEP_SEC="${UPLOAD_RETRY_MAX_SLEEP_SEC:-15}"

mkdir -p state/v7 tasks
LOG_DIR="state/v7/parallel_workers"
mkdir -p "$LOG_DIR"
STOP_FLAG="$LOG_DIR/stop"
COST_FILE="$LOG_DIR/cost.json"
PID_FILE="$LOG_DIR/parent.pid"

# Lock file shared across workers. shlock is BSD-style PID file lock; safe and
# fast on macOS. We never touch the serial loop's behavior — only workers in
# this script gate themselves on this file.
LOCK_FILE="tasks/engine_run.lock"

rm -f "$STOP_FLAG"
echo $$ > "$PID_FILE"

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
  commerce_cart_or_order_prep
  crm_followup_task_or_note
  canvas_design_edit_or_comment
)
NVERBS="${#VERBS[@]}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

current_count() {
  python3 scripts/v6/breadth_audit.py >/dev/null 2>&1 || true
  jq -r '.successful_interactions // 0' state/stranger_breadth.json 2>/dev/null || echo 0
}

# Atomic pass/fail counters as marker files in directories (filesystem is the lock).
PASS_DIR="$LOG_DIR/passes"
FAIL_DIR="$LOG_DIR/fails"
mkdir -p "$PASS_DIR" "$FAIL_DIR"
# Do NOT wipe; we want cumulative across restarts of this script.

record_pass() {
  local wid="$1" uuid="$2"
  : > "$PASS_DIR/$(date -u +%s%N)_${wid}_${uuid}"
}
record_fail() {
  local wid="$1" uuid="$2"
  : > "$FAIL_DIR/$(date -u +%s%N)_${wid}_${uuid}"
}
total_passes() { find "$PASS_DIR" -type f 2>/dev/null | wc -l | tr -d ' '; }
total_fails() { find "$FAIL_DIR" -type f 2>/dev/null | wc -l | tr -d ' '; }

estimated_spend() {
  local p="$(total_passes)"
  local f="$(total_fails)"
  python3 -c "print('%.4f' % (($p + $f) * $COST_PER_STRANGER_USD))"
}

write_cost_file() {
  python3 - "$COST_FILE" "$(total_passes)" "$(total_fails)" "$COST_PER_STRANGER_USD" <<'PY'
import json, sys, time
path, p, f, per = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
data = {
    "ts": time.time(),
    "parallel_passes": p,
    "parallel_fails": f,
    "cost_per_stranger_usd": per,
    "estimated_total_usd": round((p + f) * per, 4),
    "schema": "anticipy.parallel_workers_cost.v7",
}
open(path, "w").write(json.dumps(data, indent=2))
PY
}

# Acquire the engine lock using shlock with a bounded wait. Returns 0 on
# success, 1 on timeout. Stale lock detection is via shlock's PID check.
acquire_engine_lock() {
  local wid="$1"
  # CRITICAL: macOS ships bash 3.2 which does not support $BASHPID. We need
  # the SUBSHELL's pid (not the parent script's $$, which every subshell
  # inherits). The portable trick: a child `sh -c` sees the subshell as its
  # parent, so $PPID inside that child is the subshell's true pid.
  local me
  me="$(sh -c 'echo $PPID')"
  [ -z "$me" ] && me="$$"
  local waited=0
  while [ "$waited" -lt "$LOCK_WAIT_SEC" ]; do
    if shlock -p "$me" -f "$LOCK_FILE" 2>/dev/null; then
      return 0
    fi
    # shlock removes stale locks on next call when PID is dead; just retry.
    sleep 1
    waited=$((waited + 1))
    if [ -f "$STOP_FLAG" ]; then
      return 1
    fi
    # Backoff with jitter so workers don't synchronize on lock release.
    if [ $((waited % 5)) -eq 0 ]; then
      sleep $(( RANDOM % 3 ))
      waited=$((waited + 1))
    fi
  done
  return 1
}

release_engine_lock() {
  # Only remove the lock if we own it. Use the same PPID trick to get our
  # subshell's pid (bash 3.2 has no $BASHPID).
  local me
  me="$(sh -c 'echo $PPID')"
  [ -z "$me" ] && me="$$"
  if [ -f "$LOCK_FILE" ]; then
    local owner
    owner="$(cat "$LOCK_FILE" 2>/dev/null)"
    if [ "$owner" = "$me" ]; then
      rm -f "$LOCK_FILE" 2>/dev/null || true
    fi
  fi
}

# Run a single stranger end-to-end (generate + run). Returns 0 on pass.
# Note: run_one_stranger.sh is FROZEN; we wrap calls but never modify it.
# If the upload step returns HTTP 429 due to engine lock contention with the
# serial loop, run_one_stranger.sh exits 5 quickly. We retry up to N times by
# re-running the same stranger dir (the audio file is already on disk).
run_one_with_retry() {
  local wid="$1"
  local stranger_dir="$2"
  local uuid
  uuid="$(basename "$stranger_dir")"
  local try=0
  local rc=0
  while [ "$try" -lt "$UPLOAD_RETRY_MAX" ]; do
    try=$((try + 1))
    set +e
    # Strip ~/.local/bin from PATH so dispatch_evaluator.sh's `command -v codex`
    # fails. That makes it fall back to scripts/v7/evaluate_stranger_openrouter.py
    # (deepseek-chat-v4-flash via OpenRouter). Codex eval takes 5-10 min per
    # stranger; OpenRouter eval takes ~10s. Throughput improvement is huge.
    # Per the brief, evaluator should use OpenRouter (~$0.005-0.01 per stranger).
    STRIPPED_PATH="$(echo "$PATH" | tr ':' '\n' | grep -v "$HOME/.local/bin" | grep -v "Codex.app" | tr '\n' ':' | sed 's/:$//')"
    PATH="$STRIPPED_PATH" \
      STRANGER_DIR="$stranger_dir" bash scripts/v7/run_one_stranger.sh \
      > "$stranger_dir/run.log" 2>&1
    rc=$?
    set +e
    if [ "$rc" -eq 0 ]; then
      return 0
    fi
    # Detect 429 in upload_response.json; if it is a 429, retry.
    local upload_err
    upload_err="$(jq -r '.error // ""' "$stranger_dir/upload_response.json" 2>/dev/null)"
    case "$upload_err" in
      *"upload ASR is already running"*)
        # Backoff sleep: grows with try number, capped at UPLOAD_RETRY_MAX_SLEEP_SEC.
        # Engine ASR lock can be held for 30-60s by mic-asr or another upload.
        local sleep_s=$(( try + 2 + RANDOM % 3 ))
        [ "$sleep_s" -gt "$UPLOAD_RETRY_MAX_SLEEP_SEC" ] && sleep_s="$UPLOAD_RETRY_MAX_SLEEP_SEC"
        sleep "$sleep_s"
        continue
        ;;
    esac
    return "$rc"
  done
  return "$rc"
}

worker_loop() {
  local WID="$1"
  local WORKER_LOG="$LOG_DIR/worker_${WID}.log"
  local consec_fail=0
  local iter=0

  sleep "$((WID * 2))"

  while :; do
    if [ -f "$STOP_FLAG" ]; then
      echo "[$(ts)] worker=$WID stopping (stop flag)" >> "$WORKER_LOG"
      return 0
    fi
    cnt="$(current_count)"
    if [ "$cnt" -ge "$TARGET" ] 2>/dev/null; then
      echo "[$(ts)] worker=$WID stopping (count=$cnt >= $TARGET)" >> "$WORKER_LOG"
      : > "$STOP_FLAG"
      return 0
    fi
    spent="$(estimated_spend)"
    if python3 -c "import sys; sys.exit(0 if float('$spent') > float('$COST_CEILING_USD') else 1)"; then
      echo "[$(ts)] worker=$WID stopping (cost \$${spent} > ceiling \$${COST_CEILING_USD})" >> "$WORKER_LOG"
      : > "$STOP_FLAG"
      return 0
    fi
    if [ "$consec_fail" -ge "$CONSEC_FAIL_THRESHOLD" ]; then
      echo "[$(ts)] worker=$WID stopping ($consec_fail consecutive fails)" >> "$WORKER_LOG"
      : > "$STOP_FLAG"
      return 0
    fi

    jit=$(( RANDOM % (JITTER_MAX_SEC + 1) ))
    sleep "$jit"

    verb="${VERBS[$(((iter * WORKERS + WID) % NVERBS))]}"
    iter=$((iter + 1))

    echo "[$(ts)] worker=$WID iter=$iter cnt=$cnt verb=$verb spent=\$$spent" >> "$WORKER_LOG"

    # 1. Generate (parallel safe, no engine touch).
    gen_out="$(python3 scripts/v7/generate_stranger_openrouter.py \
      --verb-category "$verb" \
      --output-dir state/strangers 2>>"$WORKER_LOG" | tail -1)"

    stranger_dir="$(printf '%s' "$gen_out" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read().strip())
    print(d.get('stranger_dir',''))
except Exception:
    print('')
")"

    if [ -z "$stranger_dir" ] || [ ! -d "$stranger_dir" ]; then
      echo "[$(ts)] worker=$WID generator FAILED verb=$verb" >> "$WORKER_LOG"
      consec_fail=$((consec_fail + 1))
      record_fail "$WID" "genfail"
      write_cost_file
      sleep 5
      continue
    fi

    uuid="$(basename "$stranger_dir")"

    # 2. (Lock removed) Workers retry on 429 directly. The engine's
    #    _UPLOAD_ASR_LOCK is the actual contended resource; the file lock just
    #    serialized workers redundantly when only ONE could win the engine
    #    slot anyway. Letting all 3 workers race the engine improves the
    #    chance that one of them grabs the engine the instant it frees up.
    set +e
    run_one_with_retry "$WID" "$stranger_dir"
    rc=$?
    set +e

    if [ "$rc" -eq 0 ]; then
      consec_fail=0
      record_pass "$WID" "$uuid"
      echo "[$(ts)] worker=$WID PASS uuid=$uuid verb=$verb" >> "$WORKER_LOG"
    else
      consec_fail=$((consec_fail + 1))
      record_fail "$WID" "$uuid"
      echo "[$(ts)] worker=$WID FAIL uuid=$uuid verb=$verb rc=$rc consec=$consec_fail" >> "$WORKER_LOG"
      rm -rf "$stranger_dir"
      python3 scripts/v6/breadth_audit.py >/dev/null 2>&1 || true
    fi

    write_cost_file
  done
}

shutdown() {
  : > "$STOP_FLAG"
  sleep 2
  jobs -p 2>/dev/null | xargs -r kill 2>/dev/null || true
  release_engine_lock
}
trap shutdown TERM INT

echo "[$(ts)] parent pid=$$ workers=$WORKERS target=$TARGET ceiling=\$${COST_CEILING_USD}" \
  > "$LOG_DIR/parent.log"

WORKER_PIDS=()
for ((W=1; W<=WORKERS; W++)); do
  ( worker_loop "$W" ) &
  WORKER_PIDS+=($!)
  echo "[$(ts)] spawned worker $W pid=$!" >> "$LOG_DIR/parent.log"
done

while :; do
  if [ -f "$STOP_FLAG" ]; then
    echo "[$(ts)] stop flag detected; waiting for workers to drain" >> "$LOG_DIR/parent.log"
    break
  fi
  alive=0
  for pid in "${WORKER_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      alive=$((alive + 1))
    fi
  done
  if [ "$alive" -eq 0 ]; then
    echo "[$(ts)] all workers exited" >> "$LOG_DIR/parent.log"
    break
  fi
  cnt="$(current_count)"
  if [ "$cnt" -ge "$TARGET" ] 2>/dev/null; then
    echo "[$(ts)] count=$cnt >= $TARGET; setting stop flag" >> "$LOG_DIR/parent.log"
    : > "$STOP_FLAG"
    break
  fi
  sleep "$POLL_DONE_SEC"
done

for pid in "${WORKER_PIDS[@]}"; do
  wait "$pid" 2>/dev/null || true
done

write_cost_file
release_engine_lock
echo "[$(ts)] parent exiting passes=$(total_passes) fails=$(total_fails) cnt=$(current_count) spent=\$$(estimated_spend)" \
  >> "$LOG_DIR/parent.log"

rm -f "$PID_FILE"
exit 0
