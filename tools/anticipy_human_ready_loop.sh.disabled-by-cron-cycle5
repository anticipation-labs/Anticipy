#!/usr/bin/env bash
# Anticipy "human-ready" plan-fix-test loop.
#
# Goal: drive Anticipy from its current state to "a brand-new human can
# install + use it without confusion or jargon" without me babysitting.
#
# How one iteration works:
#   1. VERIFY: run the verifier. Capture a score (gates green/red, real
#      human-flow probes).
#   2. If score == DONE, write tasks/HUMAN_READY.morning + exit 0.
#   3. If score regressed vs the last good iteration, revert the most
#      recent code commit and verify again.
#   4. REPLAN: ask claude --print to read the live state + write/update
#      tasks/HUMAN_READY_PLAN.md with the next single highest-leverage
#      item to fix.
#   5. FIX: ask claude --print to execute item 1 of the plan, commit,
#      push.
#   6. Loop back to step 1.
#
# Bounded by: 8h wall clock, $10 OpenRouter, max 30 iterations.

set -u

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
cd "$REPO"
ENV_FILE="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }

LOG_DIR="state/v7/human_ready"
mkdir -p "$LOG_DIR"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/loop_${RUN_TS}.log"
PLAN="tasks/HUMAN_READY_PLAN.md"
SCORE="$LOG_DIR/score_history.jsonl"
BASELINE="$LOG_DIR/last_good_commit.txt"

START=$(date +%s)
DEADLINE=$((START + 8 * 60 * 60))
MAX_ITER=30
ITER=0

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[human_ready $(ts)] $*" | tee -a "$LOG"; }

log "loop start PID $$, log=$LOG, plan=$PLAN"

verify_human_ready() {
  # Run all human-flow probes. Print a JSON line summarizing score.
  local out="$LOG_DIR/verify_${ITER}_$(date +%s).json"

  # 1. Engine alive + bridge alive + chrome alive
  local engine_ok=false bridge_ok=false chrome_ok=false
  curl -fsS --max-time 3 http://127.0.0.1:8731/health >/dev/null 2>&1 && engine_ok=true
  curl -fsS --max-time 3 http://127.0.0.1:7777/status >/dev/null 2>&1 && bridge_ok=true
  curl -fsS --max-time 3 http://localhost:9222/json/version >/dev/null 2>&1 && chrome_ok=true

  # 2. Z-001 end-to-end (one stranger journey)
  local z001_pass=0 z001_total=0 z001_verdict="UNKNOWN"
  python3 scripts/v7/z001_e2e_harness.py > "$LOG_DIR/z001_${ITER}.log" 2>&1 || true
  local z001_dir
  z001_dir=$(ls -dt state/v7/z001_e2e_runs/* 2>/dev/null | head -1)
  if [ -n "$z001_dir" ] && [ -f "$z001_dir/result.json" ]; then
    z001_verdict=$(jq -r '.verdict // "UNKNOWN"' "$z001_dir/result.json")
    z001_pass=$(jq -r '[.steps[]? | select(.ok == true)] | length' "$z001_dir/result.json")
    z001_total=$(jq -r '.steps | length' "$z001_dir/result.json")
  fi

  # 3. 18-CHECK acceptance (skip audio per owner)
  local check_pass=0 check_total=15
  python3 engine/tests/anticipy_acceptance.py --skip 6,9,10 > "$LOG_DIR/check18_${ITER}.log" 2>&1 || true
  local acc_dir
  acc_dir=$(ls -dt proof-artifacts/acceptance_* 2>/dev/null | head -1)
  if [ -n "$acc_dir" ]; then
    for n in 01 02 03 04 05 07 08 11 12 13 14 15 16 17 18; do
      jq -e '.status == "PASS"' "$acc_dir/CHECK_${n}.json" >/dev/null 2>&1 && \
        check_pass=$((check_pass + 1))
    done
  fi

  # 4. Mac app has a visible window (human can see something)
  local mac_app_has_window=false
  if pgrep -f 'Anticipy\.app/Contents/MacOS/Anticipy' >/dev/null 2>&1; then
    local wcount
    wcount=$(osascript -e 'tell application "System Events" to tell process "Anticipy" to count of windows' 2>/dev/null || echo 0)
    [ "${wcount:-0}" -gt 0 ] 2>/dev/null && mac_app_has_window=true
  fi

  # 5. Popover.html exists (the human-facing UI surface)
  local popover_exists=false
  [ -f desktop/src/popover.html ] && popover_exists=true

  # 6. Onboarding pages reachable
  local onboard_chat=false onboard_audio=false onboard_call=false
  curl -fsS --max-time 5 -o /dev/null -w '%{http_code}' https://www.anticipy.ai/onboarding/chat 2>/dev/null | grep -q '^2' && onboard_chat=true
  curl -fsS --max-time 5 -o /dev/null -w '%{http_code}' https://www.anticipy.ai/onboarding/audio 2>/dev/null | grep -q '^2' && onboard_audio=true
  curl -fsS --max-time 5 -o /dev/null -w '%{http_code}' https://www.anticipy.ai/onboarding/call 2>/dev/null | grep -q '^2' && onboard_call=true

  # Compose score (human_ready = all true + Z-001 9/9 + 18-CHECK >=14/15)
  local human_ready=false
  if $engine_ok && $bridge_ok && $chrome_ok \
      && [ "$z001_verdict" = "PASS" ] && [ "$z001_pass" = "$z001_total" ] && [ "$z001_total" -ge 9 ] \
      && [ "$check_pass" -ge 14 ] \
      && $mac_app_has_window \
      && $popover_exists \
      && $onboard_chat && $onboard_audio && $onboard_call; then
    human_ready=true
  fi

  jq -n \
    --arg iter "$ITER" --arg ts "$(ts)" \
    --argjson eng "$engine_ok" --argjson br "$bridge_ok" --argjson ch "$chrome_ok" \
    --argjson z "$z001_pass" --argjson zt "$z001_total" --arg zv "$z001_verdict" \
    --argjson cp "$check_pass" --argjson ct "$check_total" \
    --argjson mac "$mac_app_has_window" --argjson pop "$popover_exists" \
    --argjson oc "$onboard_chat" --argjson oa "$onboard_audio" --argjson oa2 "$onboard_call" \
    --argjson done "$human_ready" \
    '{iter: ($iter|tonumber), ts: $ts, engine_ok: $eng, bridge_ok: $br, chrome_ok: $ch,
      z001: {verdict: $zv, pass: $z, total: $zt},
      check18_non_audio: {pass: $cp, total: $ct},
      mac_app_window: $mac, popover_exists: $pop,
      onboarding_pages: {chat: $oc, audio: $oa, call: $oa2},
      human_ready: $done}' > "$out"
  cat "$out" >> "$SCORE"
  cat "$out"
}

restart_engine_if_dead() {
  if ! curl -fsS --max-time 3 http://127.0.0.1:8731/health >/dev/null 2>&1; then
    log "engine dead, restarting source uvicorn"
    pkill -9 -f 'uvicorn.*8731\|anticipy-engine' 2>/dev/null
    sleep 3
    rm -f /tmp/anticipy_product_8731.lock
    cd "$REPO/engine"
    ANTICIPY_PORT=8731 ANTICIPY_ENGINE_PORT=8731 ANTICIPY_CDP_PORT=9222 \
      nohup .venv/bin/uvicorn app.product.server:app --host 127.0.0.1 --port 8731 \
      > /tmp/engine_human_ready.log 2>&1 &
    disown 2>/dev/null || true
    cd "$REPO"
    for _i in 1 2 3 4 5 6 7 8 9 10; do
      sleep 2
      curl -fsS --max-time 3 http://127.0.0.1:8731/health >/dev/null 2>&1 && break
    done
  fi
}

restart_bridge_if_dead() {
  if ! curl -fsS --max-time 3 http://127.0.0.1:7777/status >/dev/null 2>&1; then
    log "bridge dead, restarting"
    cd "$HOME/.anticipy" && pkill -f anticipy_bridge_fallback 2>/dev/null
    sleep 2
    nohup python3 ./anticipy_bridge_fallback.py > /tmp/bridge_human_ready.log 2>&1 &
    disown 2>/dev/null || true
    cd "$REPO"
    sleep 4
  fi
}

write_or_update_plan() {
  log "asking claude to write/update HUMAN_READY_PLAN.md"
  local prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Source /Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local.

You are updating tasks/HUMAN_READY_PLAN.md so the loop knows what to fix NEXT.

Goal: a brand-new human installs Anticipy from anticipy.ai, opens the Mac app, gets walked through onboarding (call OR mp3 OR chat OR ambient), starts using it without jargon. Engineering bar: Z-001 9/9 + 18-CHECK non-audio >=14/15 + popover.html exists + Mac app shows a visible window + all 3 onboarding pages reachable + status row in plain English.

Read these files first (only if relevant to your update):
  - $LOG_DIR/$(basename "$out") (latest verification score)
  - tasks/HUMAN_READY_PLAN.md (current plan)
  - desktop/src/index.html, desktop/src/popover.html (if exists), src/app/app/page.tsx (the UIs)

Rules for the plan:
  - First item = the single highest-leverage gap. The fixer agent will execute ONLY item 1.
  - Each item: 1-2 sentences + the specific file:line if known.
  - Mark items as DONE or REMOVED as state evolves.
  - Cap at 15 items. Trim the lowest-leverage when adding new ones.
  - The plan is the source of truth — be ruthless about prioritization.

Write the plan, commit, push. No em-dashes. Under 200 lines."
  local TOUT="$(command -v gtimeout || command -v timeout || true)"
  local RPT="$LOG_DIR/plan_${ITER}.log"
  if [ -n "$TOUT" ]; then
    "$TOUT" 900 claude --print --permission-mode bypassPermissions "$prompt" > "$RPT" 2>&1 || true
  else
    claude --print --permission-mode bypassPermissions "$prompt" > "$RPT" 2>&1 || true
  fi
  log "plan written; head -30:"
  head -30 "$PLAN" 2>/dev/null | tee -a "$LOG"
}

execute_top_plan_item() {
  log "asking claude to execute plan item 1"
  if [ ! -f "$PLAN" ]; then
    log "no plan file; skipping fix step"
    return
  fi
  local top_item
  top_item=$(awk '/^## 1\.|^### 1\.|^1\. |^- \[ \] /{p=1} p{print; if(/^## 2\.|^### 2\.|^2\. |^- \[ \] [^]]+$/&&NR>1)exit}' "$PLAN" 2>/dev/null | head -10)
  local prompt="Working dir /Users/omarebrahim/Developer/Anticipy-V7. Source /Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local.

tasks/HUMAN_READY_PLAN.md item 1 says:

$top_item

Execute ONLY this item. Commit + push. Verify your fix actually works by running the relevant command (one-shot) before committing. If it doesn't work, log specifically what failed and exit 0 — the loop will revert + replan.

Hard rules:
  - Don't touch frozen paths: engine/app/anticipy/, engine/app/action_engine/, engine/app/proactive_day/, verifier/.
  - Don't touch state/strangers/ except read-only.
  - Don't restart the live engine on 8731 unless absolutely necessary; if you do, source uvicorn with the same env vars (ANTICIPY_PORT=8731, ANTICIPY_ENGINE_PORT=8731, ANTICIPY_CDP_PORT=9222).
  - Don't touch the bridge or Chrome process.
  - Don't run any agent dispatch — you ARE the fixer.
  - Budget: \$1 OpenRouter per fix iteration.
  - Under 300 words in your final report."
  local TOUT="$(command -v gtimeout || command -v timeout || true)"
  local RPT="$LOG_DIR/fix_${ITER}.log"
  if [ -n "$TOUT" ]; then
    "$TOUT" 1800 claude --print --permission-mode bypassPermissions "$prompt" > "$RPT" 2>&1 || true
  else
    claude --print --permission-mode bypassPermissions "$prompt" > "$RPT" 2>&1 || true
  fi
  log "fix attempt logged at $RPT"
}

revert_last_commit_if_regression() {
  local current_check="$1"
  local last_check="$2"
  if [ "$current_check" -lt "$last_check" ]; then
    local last_good
    last_good=$(cat "$BASELINE" 2>/dev/null)
    if [ -n "$last_good" ]; then
      log "REGRESSION: check $current_check < $last_check. Reverting to $last_good"
      git reset --hard "$last_good" 2>&1 | tee -a "$LOG"
      git push --force-with-lease origin HEAD:main 2>&1 | tee -a "$LOG"
    fi
  fi
}

last_check_pass=0
while [ "$(date +%s)" -lt "$DEADLINE" ] && [ "$ITER" -lt "$MAX_ITER" ]; do
  ITER=$((ITER + 1))
  log "=== iter $ITER ==="

  restart_engine_if_dead
  restart_bridge_if_dead

  out="$LOG_DIR/verify_${ITER}_$(date +%s).json"  # for plan to read latest
  verify_json=$(verify_human_ready)
  cur_check=$(echo "$verify_json" | jq -r '.check18_non_audio.pass')
  cur_done=$(echo "$verify_json" | jq -r '.human_ready')

  if [ "$cur_done" = "true" ]; then
    log "HUMAN_READY met. Writing tasks/HUMAN_READY.morning + exiting."
    cat > tasks/HUMAN_READY.morning <<EOF
# HUMAN_READY achieved
iter: $ITER
ts: $(ts)
local_head: $(git rev-parse HEAD)
log: $LOG
verify: $(echo "$verify_json" | jq -c)
EOF
    exit 0
  fi

  revert_last_commit_if_regression "$cur_check" "$last_check_pass"

  if [ "$cur_check" -ge "$last_check_pass" ]; then
    last_check_pass="$cur_check"
    git rev-parse HEAD > "$BASELINE"
  fi

  write_or_update_plan
  execute_top_plan_item

  log "iter $ITER done. cur_check=$cur_check last_check=$last_check_pass. Sleeping 120s before next."
  sleep 120
done

cat > tasks/STILL_NOT_HUMAN_READY.morning <<EOF
# Loop hit deadline or iter cap without human_ready=true
iterations: $ITER
last_check_pass: $last_check_pass
ts: $(ts)
log: $LOG
plan: $PLAN
EOF
log "loop done without DONE"
exit 1
