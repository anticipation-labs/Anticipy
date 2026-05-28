#!/usr/bin/env bash
# V6/V7 orchestrator. Runs the Planner, Worker, Judge, stranger gate, auditors,
# ship guard, and the current done checker described in ANTICIPY_V7.md.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

BASE_BRANCH="${BASE_BRANCH:-$(git branch --show-current)}"
CYCLE_FILE="state/v6_cycle.txt"
LOG_FILE="state/orchestrator_v6.log"
CONTRACT_FILE="${CONTRACT_FILE:-ANTICIPY_V7.md}"
CHECK_DONE="${CHECK_DONE:-scripts/v7/check_done.sh}"
if [ ! -f "$CHECK_DONE" ]; then
  CHECK_DONE="scripts/v6/check_done.sh"
fi

mkdir -p state/decisions state/strangers state/mp3_eval state/builds .worktrees
[ -f "$CYCLE_FILE" ] || echo "0" > "$CYCLE_FILE"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

stop_if_needed() {
  if [ -f state/COMPLETE.md ]; then
    log "COMPLETE.md exists. Exiting 0."
    exit 0
  fi
  if [ -f state/STUCK.md ]; then
    log "STUCK.md exists. Exiting 2."
    exit 2
  fi
  if [ -f state/SETUP_BROKEN.md ]; then
    log "SETUP_BROKEN.md exists. Exiting 3."
    exit 3
  fi
}

write_setup_broken() {
  local reason="$1"
  {
    echo "SETUP_BROKEN"
    echo "Reason: $reason"
    echo "At: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > state/SETUP_BROKEN.md
  log "SETUP_BROKEN: $reason"
}

require_contract() {
  if ! grep -q "public downloadable user-device engine" "$CONTRACT_FILE" 2>/dev/null; then
    write_setup_broken "$CONTRACT_FILE missing or does not contain the V7 public product target"
    exit 3
  fi
}

run_regression_snapshot() {
  local cycle="$1"
  local dir="state/cycle-$cycle"
  mkdir -p "$dir"
  bash scripts/regression.sh > "$dir/regression.log" 2>&1 || true
}

dispatch_planner() {
  local cycle="$1"
  local dir="state/cycle-$cycle"
  mkdir -p "$dir"
  CYCLE="$cycle" CYCLE_DIR="$dir" bash scripts/v6/dispatch_planner.sh \
    > "$dir/planner.dispatch.log" 2>&1
  if [ ! -f "$dir/tasks.json" ] && [ ! -f state/COMPLETE.md ]; then
    write_setup_broken "planner did not write $dir/tasks.json"
    return 1
  fi
}

dispatch_workers() {
  local cycle="$1"
  local dir="state/cycle-$cycle"
  local count
  count=$(jq '.tasks | length' "$dir/tasks.json")
  jq -e '.tasks | type == "array"' "$dir/tasks.json" >/dev/null
  for i in $(seq 0 $((count - 1))); do
    local id branch worktree task_file
    id=$(jq -r ".tasks[$i].id" "$dir/tasks.json")
    branch="v6-$id"
    worktree=".worktrees/$id"
    task_file="$REPO/$dir/task-$id.json"
    jq ".tasks[$i]" "$dir/tasks.json" > "$task_file"
    if [ -d "$worktree" ]; then
      git worktree remove "$worktree" --force 2>/dev/null || rm -rf "$worktree"
    fi
    if git show-ref --verify --quiet "refs/heads/$branch"; then
      git branch -D "$branch" >/dev/null 2>&1 || true
    fi
    git worktree add -b "$branch" "$worktree" "$BASE_BRANCH"
    CYCLE="$cycle" CYCLE_DIR="$dir" TASK_ID="$id" WORKTREE="$worktree" TASK_FILE="$task_file" \
      bash scripts/v6/dispatch_worker.sh > "$dir/worker-$id.dispatch.log" 2>&1 || true
  done
}

run_success_tests() {
  local cycle="$1"
  local dir="state/cycle-$cycle"
  local count results
  count=$(jq '.tasks | length' "$dir/tasks.json")
  results="{}"
  for i in $(seq 0 $((count - 1))); do
    local id worktree cmd stdout stderr code
    id=$(jq -r ".tasks[$i].id" "$dir/tasks.json")
    cmd=$(jq -r ".tasks[$i].success_test" "$dir/tasks.json")
    worktree=".worktrees/$id"
    stdout="$dir/test-$id.stdout"
    stderr="$dir/test-$id.stderr"
    code=0
    (cd "$worktree" && env -u REPO REGRESSION_SKIP_DEPLOY_PARITY=1 \
      python3 "$REPO/scripts/v6/run_with_timeout.py" \
      "${SUCCESS_TEST_TIMEOUT_SECONDS:-900}" bash -lc "$cmd") \
      > "$stdout" 2> "$stderr" || code=$?
    results=$(printf '%s' "$results" | jq \
      --arg id "$id" \
      --argjson code "$code" \
      --rawfile out "$stdout" \
      --rawfile err "$stderr" \
      '.[$id] = {exit_code: $code, stdout: $out, stderr: $err}')
  done
  printf '%s\n' "$results" > "$dir/success_test_results.json"
}

dispatch_judge() {
  local cycle="$1"
  local dir="state/cycle-$cycle"
  local count diffs
  count=$(jq '.tasks | length' "$dir/tasks.json")
  diffs="{}"
  for i in $(seq 0 $((count - 1))); do
    local id worktree diff_file
    id=$(jq -r ".tasks[$i].id" "$dir/tasks.json")
    worktree=".worktrees/$id"
    diff_file="$dir/diff-$id.patch"
    # Judge only the committed worker diff. Success tests intentionally write
    # generated state under state/, and those receipts must not make a scoped
    # worker look out-of-scope.
    (cd "$worktree" && git diff "$BASE_BRANCH...HEAD" -- .) > "$diff_file" || true
    diffs=$(printf '%s' "$diffs" | jq --arg id "$id" --rawfile d "$diff_file" '.[$id] = $d')
  done
  jq -n \
    --argjson cycle "$cycle" \
    --slurpfile tasks "$dir/tasks.json" \
    --slurpfile results "$dir/success_test_results.json" \
    --argjson diffs "$diffs" \
    '{cycle: $cycle, tasks: $tasks[0].tasks, success_test_results: $results[0], worktree_diffs: $diffs}' \
    > "$dir/judge_input.json"
  CYCLE="$cycle" CYCLE_DIR="$dir" JUDGE_INPUT="$dir/judge_input.json" \
    bash scripts/v6/dispatch_judge.sh > "$dir/judge.dispatch.log" 2>&1 || true
  [ -f "$dir/judge_verdict.json" ] || write_setup_broken "judge did not write $dir/judge_verdict.json"
}

apply_verdicts() {
  local cycle="$1"
  local dir="state/cycle-$cycle"
  local verdicts
  verdicts=$(jq '.verdicts | length' "$dir/judge_verdict.json")
  for i in $(seq 0 $((verdicts - 1))); do
    local id branch decision worktree before after
    id=$(jq -r ".verdicts[$i].task_id" "$dir/judge_verdict.json")
    branch="v6-$id"
    decision=$(jq -r ".verdicts[$i].decision" "$dir/judge_verdict.json")
    worktree=".worktrees/$id"
    if [ "$decision" = "merge" ]; then
      before=$(git rev-parse HEAD)
      git checkout "$BASE_BRANCH"
      if git merge --no-ff "$branch" -m "merge: $id (V6 cycle $cycle)"; then
        after=$(git rev-parse HEAD)
        BEFORE="$before" AFTER="$after" bash scripts/v6/ship_if_bundled.sh \
          > "$dir/ship-$id.log" 2>&1 || true
      else
        git merge --abort || true
      fi
    fi
    git worktree remove "$worktree" --force 2>/dev/null || rm -rf "$worktree"
    git branch -D "$branch" >/dev/null 2>&1 || true
  done
}

run_stranger_gate() {
  local cycle="$1"
  local dir="state/cycle-$cycle"
  local manifest="$dir/stranger_manifest.json"
  CYCLE="$cycle" CYCLE_DIR="$dir" bash scripts/v6/dispatch_stranger_generator.sh \
    > "$dir/stranger_generator.dispatch.log" 2>&1 || true
  local latest
  latest=$(find state/strangers -mindepth 1 -maxdepth 1 -type d -print0 | xargs -0 ls -td 2>/dev/null | head -1 || true)
  if [ -z "$latest" ]; then
    echo '{"ok": false, "reason": "no stranger generated"}' > "$manifest"
    return
  fi
  local baseline
  baseline=$(bash scripts/v6/state_hygiene.sh "$(basename "$latest")" || true)
  jq -n --arg stranger_dir "$latest" --arg baseline "$baseline" \
    '{stranger_dir: $stranger_dir, baseline: $baseline}' > "$manifest"
  set +e
  python3 scripts/v7/select_stranger_driver.py \
    --stranger-dir "$latest" \
    --persona-file "$latest/persona.json" \
    --script-file "$latest/script.json" \
    > "$latest/driver.dispatch.log" 2>&1
  local driver_rc=$?
  set -e
  if [ "$driver_rc" -eq 2 ]; then
    PERSONA_FILE="$latest/persona.json" SCRIPT_FILE="$latest/script.json" STRANGER_DIR="$latest" \
      bash scripts/v6/dispatch_stranger_driver.sh >> "$latest/driver.dispatch.log" 2>&1 || true
  fi
  local -a receipt_args=(--stranger-dir "$latest")
  if [ -n "${ANTICIPY_ENGINE_URL:-}" ]; then
    receipt_args+=(--engine-url "$ANTICIPY_ENGINE_URL")
  fi
  python3 scripts/v6/write_stranger_receipts.py "${receipt_args[@]}" > "$latest/receipts.log" 2>&1 || true
  python3 verifier/v6/trace_reader.py --out "$latest/trace.json" --stranger-dir "$latest" --baseline "$baseline" \
    > "$latest/trace_reader.log" 2>&1 || true
  PERSONA_FILE="$latest/persona.json" SCRIPT_FILE="$latest/script.json" TRACE_FILE="$latest/trace.json" \
    STRANGER_DIR="$latest" bash scripts/v6/dispatch_evaluator.sh > "$latest/evaluator.dispatch.log" 2>&1 || true
}

run_mp3_if_due() {
  local cycle="$1"
  local due_file="state/cycle-$cycle/mp3_due.json"
  if ! python3 scripts/v6/mp3_due.py --cycle "$cycle" --state-dir state > "$due_file"; then
    log "MP3 evaluation not due for cycle $cycle."
    return
  fi
  log "MP3 evaluation due for cycle $cycle: $(jq -r '.reason' "$due_file")"
  local dir="state/mp3_eval/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$dir"
  printf '{"cycle":%s,"created_at":"%s"}\n' "$cycle" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$dir/cycle.json"
  if [ -f scripts/mp3_eval.sh ]; then
    bash scripts/mp3_eval.sh > "$dir/mp3_eval.log" 2>&1 || true
  else
    echo '{"pass": false, "reason": "scripts/mp3_eval.sh missing"}' > "$dir/verdict.json"
  fi
}

update_status() {
  local cycle="$1"
  python3 scripts/v6/breadth_audit.py --write-status >/dev/null 2>&1 || true
  python3 scripts/v6/cost_audit.py >/dev/null 2>&1 || true
  python3 scripts/v6/transcript_audit.py >/dev/null 2>&1 || true
  {
    echo "# V7 STATUS"
    echo
    echo "Cycle: $cycle"
    echo "Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Local HEAD: $(git rev-parse HEAD)"
    echo "Origin main: $(git ls-remote origin refs/heads/main | awk '{print $1}')"
    echo "Live commit: $(curl -sS https://www.anticipy.ai/api/app/state | jq -r '.build.commit // .commit // .deployedCommit // empty' || true)"
    echo
    [ -f state/stranger_breadth.json ] && cat state/stranger_breadth.json
    echo
    [ -f state/last_v6_cost_audit.json ] && cat state/last_v6_cost_audit.json
    echo
    [ -f state/last_v6_transcript_audit.json ] && cat state/last_v6_transcript_audit.json
  } > state/STATUS.md
}

main() {
  require_contract
  log "V7-corrected orchestrator starting on $BASE_BRANCH in $REPO"
  while true; do
    stop_if_needed
    local cycle
    cycle=$(( $(cat "$CYCLE_FILE") + 1 ))
    echo "$cycle" > "$CYCLE_FILE"
    log "==== V7 cycle $cycle ===="
    bash scripts/v6/disk_hygiene.sh >/dev/null 2>&1 || true
    run_regression_snapshot "$cycle"
    dispatch_planner "$cycle" || stop_if_needed
    stop_if_needed
    dispatch_workers "$cycle"
    run_success_tests "$cycle"
    dispatch_judge "$cycle"
    stop_if_needed
    apply_verdicts "$cycle"
    run_stranger_gate "$cycle"
    run_mp3_if_due "$cycle"
    update_status "$cycle"
    if bash "$CHECK_DONE" > "state/cycle-$cycle/check_done.log" 2>&1; then
      log "V7 done check passed. COMPLETE.md written."
      exit 0
    fi
    log "==== V7 cycle $cycle complete ===="
    sleep "${V6_CYCLE_SLEEP_SECONDS:-30}"
  done
}

main "$@"
