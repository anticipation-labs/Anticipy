#!/usr/bin/env bash
# orchestrate.sh — the autonomous loop
#
# Architecture: Cursor's planner-worker-judge pattern (proven on 1M-line browser, Jan 2026).
# Each role runs in a fresh Codex sub-session via `codex exec` (non-interactive mode).
# Workers run in isolated git worktrees. No collisions.
#
# This script runs forever. Stop conditions:
#   - state/COMPLETE.md written (all DONE.md criteria green + 3 MP3 evals + 3 stranger runs)
#   - state/STUCK.md written (3 cycles same root cause)
#   - state/SETUP_BROKEN.md written (codex exec doesn't work)

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"
BASE_BRANCH="${BASE_BRANCH:-$(git branch --show-current)}"

mkdir -p state/decisions .worktrees

CYCLE_FILE="state/cycle.txt"
[ -f "$CYCLE_FILE" ] || echo "0" > "$CYCLE_FILE"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a state/orchestrator.log
}

failure_codes_from_log() {
  local log_file=$1
  if [ ! -f "$log_file" ]; then
    return 0
  fi
  grep -E "^FAIL: E[0-9]+:" "$log_file" \
    | sed -E "s/^FAIL: (E[0-9]+):.*/\\1/" \
    | sort -u || true
}

new_failure_codes() {
  local before_log=$1
  local after_log=$2
  local ignore_e0="${3:-0}"
  local before_codes after_codes
  before_codes=$(mktemp)
  after_codes=$(mktemp)
  failure_codes_from_log "$before_log" > "$before_codes"
  failure_codes_from_log "$after_log" > "$after_codes"
  if [ "$ignore_e0" = "1" ]; then
    comm -13 "$before_codes" "$after_codes" | grep -v "^E0$" || true
  else
    comm -13 "$before_codes" "$after_codes" || true
  fi
  rm -f "$before_codes" "$after_codes"
}

write_stuck_for_shipped_regression() {
  local cycle=$1
  local task_id=$2
  local artifact=$3
  {
    echo "# STUCK"
    echo
    echo "Cycle: $cycle"
    echo "Task: $task_id"
    echo "Reason: regression introduced new failure codes after a task that was already shipped to origin/$BASE_BRANCH."
    echo "Artifact: $artifact"
  } > state/STUCK.md
}

head_requires_dmg_ship() {
  local base_commit=$1
  git diff --name-only "$base_commit" HEAD \
    | grep -E "^(engine/|desktop/|src-tauri/|Cargo\\.lock|Cargo\\.toml)" >/dev/null 2>&1
}

poll_live_commit() {
  local expected_short=$1
  local live_commit=""
  for i in $(seq 1 60); do
    live_commit=$(curl -s -H "Cache-Control: no-cache" "https://www.anticipy.ai/api/app/state?poll=$expected_short-$i" | jq -r '.build.commit // .commit // .deployedCommit // empty' || echo "")
    if [ "${live_commit:0:7}" = "$expected_short" ]; then
      return 0
    fi
    log "  live=$live_commit expected=$expected_short (try $i/60)"
    sleep 10
  done
  return 1
}

ship_head_if_needed() {
  local cycle=$1
  local task_id=$2
  local base_commit=$3
  local cycle_dir="state/cycle-$cycle"
  local head_short live_commit
  head_short=$(git rev-parse --short HEAD)
  live_commit=$(curl -s -H "Cache-Control: no-cache" "https://www.anticipy.ai/api/app/state?ship=$head_short" | jq -r '.build.commit // .commit // .deployedCommit // empty' || echo "")
  if [ "${live_commit:0:7}" = "$head_short" ]; then
    log "  Live site already matches $head_short"
    return 0
  fi
  if head_requires_dmg_ship "$base_commit"; then
    log "  Shipping $task_id with full DMG rebuild so live site matches $head_short"
    bash scripts/ship.sh > "$cycle_dir/ship-$task_id.log" 2>&1
    return
  fi

  log "  Pushing $task_id as code-only deploy so live site matches $head_short"
  {
    git push origin HEAD:main
    poll_live_commit "$head_short"
  } > "$cycle_dir/ship-$task_id.log" 2>&1
}

stop_if_complete() {
  if [ -f state/COMPLETE.md ]; then
    log "COMPLETE.md exists. Done. Exiting 0."
    exit 0
  fi
  if [ -f state/STUCK.md ]; then
    log "STUCK.md exists. Exiting non-zero so Omar sees it."
    exit 2
  fi
  if [ -f state/SETUP_BROKEN.md ]; then
    log "SETUP_BROKEN.md exists. Exiting non-zero."
    exit 3
  fi
}

dispatch_planner() {
  local cycle=$1
  local cycle_dir="state/cycle-$cycle"
  mkdir -p "$cycle_dir"
  log "Cycle $cycle: dispatching Planner."
  CYCLE=$cycle CYCLE_DIR="$cycle_dir" bash scripts/dispatch_planner.sh
  if [ ! -f "$cycle_dir/tasks.json" ] && [ ! -f state/COMPLETE.md ]; then
    log "Planner did not produce tasks.json. Treating as transient. Sleeping 60s."
    sleep 60
    return 1
  fi
  return 0
}

dispatch_workers() {
  local cycle=$1
  local cycle_dir="state/cycle-$cycle"
  local task_count
  task_count=$(jq '.tasks | length' "$cycle_dir/tasks.json")
  log "Cycle $cycle: dispatching $task_count Workers."

  for i in $(seq 0 $((task_count - 1))); do
    local task_id
    task_id=$(jq -r ".tasks[$i].id" "$cycle_dir/tasks.json")
    local worktree=".worktrees/$task_id"
    log "  Worker $task_id → worktree $worktree"

    if [ -d "$worktree" ]; then
      git worktree remove "$worktree" --force 2>/dev/null || rm -rf "$worktree"
    fi
    git worktree add -b "$task_id" "$worktree" "$BASE_BRANCH"

    jq ".tasks[$i]" "$cycle_dir/tasks.json" > "$cycle_dir/task-$task_id.json"

    CYCLE=$cycle CYCLE_DIR="$cycle_dir" TASK_ID="$task_id" \
      WORKTREE="$worktree" TASK_FILE="$cycle_dir/task-$task_id.json" \
      bash scripts/dispatch_worker.sh &
  done
  wait
  log "Cycle $cycle: all Workers exited."
}

run_success_tests() {
  local cycle=$1
  local cycle_dir="state/cycle-$cycle"
  local task_count
  task_count=$(jq '.tasks | length' "$cycle_dir/tasks.json")
  local results="{}"

  for i in $(seq 0 $((task_count - 1))); do
    local task_id
    task_id=$(jq -r ".tasks[$i].id" "$cycle_dir/tasks.json")
    local test_cmd
    test_cmd=$(jq -r ".tasks[$i].success_test" "$cycle_dir/tasks.json")
    local worktree=".worktrees/$task_id"

    log "  Running success_test for $task_id in $worktree"
    local stdout_f="$cycle_dir/test-$task_id.stdout"
    local stderr_f="$cycle_dir/test-$task_id.stderr"
    local exit_code=0
    (cd "$worktree" && bash -c "$test_cmd") > "$stdout_f" 2> "$stderr_f" || exit_code=$?

    results=$(echo "$results" | jq \
      --arg id "$task_id" \
      --arg ec "$exit_code" \
      --rawfile so "$stdout_f" \
      --rawfile se "$stderr_f" \
      '.[$id] = {exit_code: ($ec | tonumber), stdout: $so, stderr: $se}')
  done
  echo "$results" > "$cycle_dir/success_test_results.json"
}

dispatch_judge() {
  local cycle=$1
  local cycle_dir="state/cycle-$cycle"
  log "Cycle $cycle: dispatching Judge."

  local diffs="{}"
  local task_count
  task_count=$(jq '.tasks | length' "$cycle_dir/tasks.json")
  for i in $(seq 0 $((task_count - 1))); do
    local task_id
    task_id=$(jq -r ".tasks[$i].id" "$cycle_dir/tasks.json")
    local worktree=".worktrees/$task_id"
    local diff
    diff=$(cd "$worktree" && git diff "$BASE_BRANCH" -- . 2>/dev/null || echo "")
    diffs=$(echo "$diffs" | jq --arg id "$task_id" --arg d "$diff" '.[$id] = $d')
  done

  jq -n \
    --arg cycle "$cycle" \
    --slurpfile tasks "$cycle_dir/tasks.json" \
    --argjson diffs "$diffs" \
    --slurpfile results "$cycle_dir/success_test_results.json" \
    '{cycle: ($cycle | tonumber), tasks: $tasks[0].tasks, worktree_diffs: $diffs, success_test_results: $results[0]}' \
    > "$cycle_dir/judge_input.json"

  CYCLE=$cycle CYCLE_DIR="$cycle_dir" JUDGE_INPUT="$cycle_dir/judge_input.json" \
    bash scripts/dispatch_judge.sh
}

apply_verdicts() {
  local cycle=$1
  local cycle_dir="state/cycle-$cycle"
  local verdict_file="$cycle_dir/judge_verdict.json"
  if [ ! -f "$verdict_file" ]; then
    log "  Judge did not produce verdict. Treating as escalate-all."
    return 1
  fi

  local verdict_count
  verdict_count=$(jq '.verdicts | length' "$verdict_file")
  local any_merge_failed=0

  for i in $(seq 0 $((verdict_count - 1))); do
    local task_id decision
    task_id=$(jq -r ".verdicts[$i].task_id" "$verdict_file")
    decision=$(jq -r ".verdicts[$i].decision" "$verdict_file")
    local worktree=".worktrees/$task_id"

    case "$decision" in
      merge)
        log "  Merging $task_id"
        git checkout "$BASE_BRANCH"
        git fetch origin "$BASE_BRANCH" >/dev/null 2>&1 || true
        local pre_merge_head
        pre_merge_head=$(git rev-parse HEAD)
        local baseline_log
        baseline_log="$cycle_dir/regression-before-$task_id.log"
        log "  Capturing baseline regression failures before $task_id"
        bash scripts/regression.sh > "$baseline_log" 2>&1 || true

        if git merge-base --is-ancestor "$task_id" "origin/$BASE_BRANCH" 2>/dev/null; then
          log "  $task_id is already on origin/$BASE_BRANCH from ship.sh; fast-forwarding local $BASE_BRANCH"
          git reset --hard "origin/$BASE_BRANCH"
        elif git merge --no-ff "$task_id" -m "merge: $task_id (cycle $cycle)"; then
          true
        else
          log "  Merge conflict on $task_id. Reverting."
          git merge --abort || true
          any_merge_failed=1
          continue
        fi

        local pre_ship_log pre_ship_new_codes
        pre_ship_log="$cycle_dir/regression-pre-ship-$task_id.log"
        log "  Running pre-ship regression after merge of $task_id"
        bash scripts/regression.sh > "$pre_ship_log" 2>&1 || true
        pre_ship_new_codes=$(new_failure_codes "$baseline_log" "$pre_ship_log" 1)
        if [ -n "$pre_ship_new_codes" ]; then
          log "  Pre-ship regression introduced new failures for $task_id: $pre_ship_new_codes. Reverting."
          if git merge-base --is-ancestor "$task_id" "origin/$BASE_BRANCH" 2>/dev/null; then
            write_stuck_for_shipped_regression "$cycle" "$task_id" "$pre_ship_log"
          else
            git reset --hard HEAD~1
          fi
          any_merge_failed=1
          continue
        fi

        if ! ship_head_if_needed "$cycle" "$task_id" "$pre_merge_head"; then
          log "  ship.sh FAIL for merged $task_id. Reverting merge."
          git reset --hard HEAD~1
          any_merge_failed=1
          continue
        fi

        local post_ship_log post_ship_new_codes
        post_ship_log="$cycle_dir/regression-$task_id.log"
        log "  Running post-ship regression after merge of $task_id"
        if bash scripts/regression.sh > "$post_ship_log" 2>&1; then
          log "  Regression PASS for $task_id"
        else
          post_ship_new_codes=$(new_failure_codes "$baseline_log" "$post_ship_log")
          if [ -z "$post_ship_new_codes" ]; then
            log "  Regression still has existing failures after $task_id, but introduced no new failure codes."
          else
            log "  Regression introduced new failures for $task_id after ship: $post_ship_new_codes."
            write_stuck_for_shipped_regression "$cycle" "$task_id" "$post_ship_log"
            any_merge_failed=1
          fi
        fi
        ;;
      reject)
        log "  Rejected $task_id. Worktree branch kept for inspection."
        ;;
      escalate)
        log "  Escalated $task_id. Routing to next cycle."
        ;;
    esac

    git worktree remove "$worktree" --force 2>/dev/null || rm -rf "$worktree"
  done

  return $any_merge_failed
}

run_mp3_eval_if_due() {
  local cycle=$1
  if [ $((cycle % 5)) -eq 0 ] && [ "$cycle" -gt 0 ]; then
    log "Cycle $cycle: running held-out MP3 eval."
    bash scripts/mp3_eval.sh > "state/cycle-$cycle/mp3_eval.log" 2>&1 || true
  fi
}

write_status() {
  local cycle=$1
  bash scripts/write_status.sh "$cycle" || true
}

check_stuck() {
  local cycle=$1
  if [ "$cycle" -lt 3 ]; then return; fi
  local last_three_status
  last_three_status=$(jq -r '.verdicts[] | .decision' \
    "state/cycle-$cycle/judge_verdict.json" \
    "state/cycle-$((cycle-1))/judge_verdict.json" \
    "state/cycle-$((cycle-2))/judge_verdict.json" 2>/dev/null | sort -u || echo "")
  if [ "$last_three_status" = "reject" ]; then
    local last_three_tasks
    last_three_tasks=$(jq -r '.verdicts[] | .task_id' \
      "state/cycle-$cycle/judge_verdict.json" \
      "state/cycle-$((cycle-1))/judge_verdict.json" \
      "state/cycle-$((cycle-2))/judge_verdict.json" | sort -u)
    log "STUCK: 3 consecutive cycles, all rejected. Tasks: $last_three_tasks"
    {
      echo "# STUCK"
      echo
      echo "Cycle: $cycle"
      echo "Tasks repeatedly rejected: $last_three_tasks"
      echo
      echo "Read state/decisions/queue.md for the workaround default that was applied."
      echo "If the loop should resume, delete this file and the orchestrator picks back up."
    } > state/STUCK.md
  fi
}

main() {
  log "Orchestrator starting. Repo: $REPO Base branch: $BASE_BRANCH"
  stop_if_complete

  while true; do
    stop_if_complete
    local cycle
    cycle=$(($(cat "$CYCLE_FILE") + 1))
    echo "$cycle" > "$CYCLE_FILE"
    log "==== Cycle $cycle ===="

    dispatch_planner "$cycle" || { sleep 60; continue; }

    if [ -f state/COMPLETE.md ]; then
      log "Planner wrote COMPLETE.md. Validating with final regression + final MP3 eval."
      if bash scripts/regression.sh && bash scripts/mp3_eval.sh; then
        log "Final validation passed. Exiting 0."
        exit 0
      else
        log "Planner wrote COMPLETE.md but final validation failed. Removing COMPLETE.md, continuing."
        rm state/COMPLETE.md
      fi
    fi

    dispatch_workers "$cycle"
    run_success_tests "$cycle"
    dispatch_judge "$cycle"
    apply_verdicts "$cycle" || log "Cycle $cycle: at least one merge reverted."
    run_mp3_eval_if_due "$cycle"
    write_status "$cycle"
    check_stuck "$cycle"

    log "==== Cycle $cycle complete. Sleeping 30s. ===="
    sleep 30
  done
}

main "$@"
