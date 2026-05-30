#!/usr/bin/env bash
# Anticipy Master Supervisor (Ralph Loop System).
# bash 3.2 compatible (macOS default).

set -u

REPO="${REPO:-/Users/omarebrahim/Developer/Anticipy-V7}"
cd "$REPO"

ENV_FILE="${ANTICIPY_ENV_FILE:-/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local}"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }

mkdir -p tasks state/v7/supervisor
STOP_FILE="tasks/anticipy_supervisor.stop"
PID_FILE="tasks/anticipy_supervisor.pid"
LOG_DIR="state/v7/supervisor"
STATUS_FILE="state/v7/supervisor_status.json"

rm -f "$STOP_FILE"
echo $$ > "$PID_FILE"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[supervisor $(ts)] $*" >> "$LOG_DIR/supervisor.log"; }

log "supervisor PID=$$ starting"

loop_health() {
  while [ ! -f "$STOP_FILE" ]; do
    if ! lsof -nP -iTCP:8731 -sTCP:LISTEN >/dev/null 2>&1; then
      echo "[health $(ts)] engine dead; relaunching /Applications/Anticipy.app" >> "$LOG_DIR/health.log"
      # Prefer the installed app so V7.3 + V7.10 + evaluator Rule 4 stay green.
      # Dev uvicorn was breaking these gates by binding port 8731 with the wrong command_token.
      if [ -d /Applications/Anticipy.app ]; then
        # Launch the engine binary directly with ANTICIPY_PORT=8731 pinned.
        # `open Anticipy.app` runs the GUI which picks a random free port (e.g. 64360)
        # since the launchd plist is disabled. We need 8731 specifically so check_done /
        # supervisor / stranger probes all hit it without reading the engine.port file.
        rm -f /tmp/anticipy_product_8731.lock 2>/dev/null
        # ANTICIPY_CDP_PORT=9222 tells _ensure_cdp_chrome where the user's real
        # Chrome is debugging on. Without it, /api/act gates with "No real Chrome
        # on :9222" and plans never reach make_real_action_engine.
        ANTICIPY_PORT=8731 ANTICIPY_ENGINE_PORT=8731 ANTICIPY_CDP_PORT=9222 \
          nohup /Applications/Anticipy.app/Contents/MacOS/anticipy-engine \
          >> "$LOG_DIR/engine.log" 2>&1 &
        disown 2>/dev/null || true
        for _try in 1 2 3 4 5 6 7 8 9 10; do
          sleep 3
          lsof -nP -iTCP:8731 -sTCP:LISTEN >/dev/null 2>&1 && break
        done
      else
        echo "[health $(ts)] WARNING /Applications/Anticipy.app missing; falling back to dev uvicorn" >> "$LOG_DIR/health.log"
        ( cd "$REPO/engine" && nohup .venv/bin/uvicorn app.product.server:app --host 127.0.0.1 --port 8731 \
          >> "$REPO/$LOG_DIR/engine.log" 2>&1 & )
        sleep 10
      fi
    fi
    if ! lsof -nP -iTCP:7777 -sTCP:LISTEN >/dev/null 2>&1; then
      echo "[health $(ts)] bridge dead; restarting" >> "$LOG_DIR/health.log"
      ( cd "$HOME/.anticipy" && nohup python3 ./anticipy_bridge_fallback.py \
        >> "$REPO/$LOG_DIR/bridge.log" 2>&1 & )
      sleep 5
    fi
    if ! curl -fsS --max-time 3 http://localhost:9222/json/version >/dev/null 2>&1; then
      echo "[health $(ts)] chrome 9222 down (no autorestart)" >> "$LOG_DIR/health.log"
    fi
    sleep 60
  done
}

loop_strangers() {
  while [ ! -f "$STOP_FILE" ]; do
    cnt=$(jq -r '.successful_interactions // 0' state/stranger_breadth.json 2>/dev/null || echo 0)
    if [ "$cnt" -ge 100 ] 2>/dev/null; then
      echo "[strangers $(ts)] hit $cnt; idling 600s" >> "$LOG_DIR/strangers_loop.log"
      sleep 600
      continue
    fi
    echo "[strangers $(ts)] start run_until_100 (current=$cnt)" >> "$LOG_DIR/strangers_loop.log"
    bash scripts/v7/run_until_100.sh 100 >> "$LOG_DIR/strangers.log" 2>&1 || true
    echo "[strangers $(ts)] batch exited; sleeping 30" >> "$LOG_DIR/strangers_loop.log"
    sleep 30
  done
}

loop_v7_gates() {
  while [ ! -f "$STOP_FILE" ]; do
    bash tools/ralph_v7.sh >> "$LOG_DIR/ralph_v7.log" 2>&1 || true
    echo "[ralph $(ts)] exited; sleeping 60" >> "$LOG_DIR/ralph_loop.log"
    sleep 60
  done
}

loop_ralph_trillion() {
  while [ ! -f "$STOP_FILE" ]; do
    if [ -f "$REPO/tasks/DONE.md.trillion" ]; then
      echo "[trillion $(ts)] DONE.md.trillion present; idling 600s" >> "$LOG_DIR/ralph_trillion_loop.log"
      sleep 600
      continue
    fi
    if [ -x tools/ralph_trillion.sh ] && [ -x scripts/v7/trillion_dollar_check.sh ]; then
      bash tools/ralph_trillion.sh >> "$LOG_DIR/ralph_trillion_loop.log" 2>&1 || true
      echo "[trillion $(ts)] iteration exited; sleeping 300" >> "$LOG_DIR/ralph_trillion_loop.log"
      sleep 300
    else
      echo "[trillion $(ts)] WAIT: ralph_trillion.sh or trillion_dollar_check.sh missing or not executable; sleeping 120" >> "$LOG_DIR/ralph_trillion_loop.log"
      sleep 120
    fi
  done
}

loop_autocommit() {
  # Tighter scope: only commit deliberate engine/script/doc work + small state.
  # NEVER stage state/v7/clean_room_public_install_runs/ (it holds 1-2 GiB DMG copies
  # that triggered the GitHub > 2 GiB blob limit on a prior pass).
  while [ ! -f "$STOP_FILE" ]; do
    cd "$REPO"
    git add scripts/v7/*.sh scripts/v7/*.py scripts/v6/*.sh scripts/v6/*.py \
      state/strangers/*/verdict.json state/strangers/*/trace.json state/stranger_breadth.json \
      state/check_done_v7.json state/builds/manifest.json state/v7/*.md state/v7/*.json \
      engine/app/product/*.py docs/*.md tools/*.sh .gitignore 2>/dev/null || true
    git reset HEAD state/v7/clean_room_public_install_runs/ 2>/dev/null || true
    if git diff --cached 2>/dev/null | rg -i 'OPENROUTER_API_KEY|sk-or-|R2_SECRET|SERVICE_ROLE|PRIVATE_KEY|ACCESS_KEY=' >/dev/null 2>&1; then
      echo "[autocommit $(ts)] SECRET DETECTED; reset" >> "$LOG_DIR/autocommit.log"
      git reset HEAD 2>/dev/null
    elif ! git diff --cached --quiet 2>/dev/null; then
      # Refuse to commit anything > 50 MiB; that's a sign of accidental binary inclusion.
      BIG=$(git diff --cached --numstat 2>/dev/null | awk '{print $3}' | xargs -I{} sh -c 'f="{}"; [ -f "$f" ] && wc -c < "$f"' 2>/dev/null | awk '$1>52428800{print; exit}')
      if [ -n "$BIG" ]; then
        echo "[autocommit $(ts)] OVERSIZED BLOB in staged set; aborting commit" >> "$LOG_DIR/autocommit.log"
        git reset HEAD 2>/dev/null
      else
        git commit -m "supervisor: autocommit progress checkpoint" >> "$LOG_DIR/autocommit.log" 2>&1 || true
        git push origin HEAD:main >> "$LOG_DIR/autocommit.log" 2>&1 || true
      fi
    fi
    sleep 300
  done
}

loop_status() {
  while [ ! -f "$STOP_FILE" ]; do
    cd "$REPO"
    ENGINE_PID=$(lsof -t -iTCP:8731 -sTCP:LISTEN 2>/dev/null | head -1)
    BRIDGE_PID=$(lsof -t -iTCP:7777 -sTCP:LISTEN 2>/dev/null | head -1)
    CHROME=$(curl -fsS --max-time 2 http://localhost:9222/json/version 2>/dev/null | jq -r '.Browser // ""')
    STR_ALIVE=$(pgrep -af 'run_one_stranger|run_batch_strangers|run_until_100' | wc -l | tr -d ' ')
    RALPH_ALIVE=$(pgrep -af 'ralph_v7\.sh' | wc -l | tr -d ' ')
    SUP_ALIVE=$(pgrep -af 'anticipy_supervisor\.sh' | wc -l | tr -d ' ')
    BREADTH=$(cat state/stranger_breadth.json 2>/dev/null || echo null)
    GATE_GREEN=$(jq -r '[.gates[] | select(. == true)] | length' state/check_done_v7.json 2>/dev/null || echo 0)
    GATE_RED=$(jq '[.gates | to_entries[] | select(.value == false) | .key]' state/check_done_v7.json 2>/dev/null || echo null)
    LIVE=$(curl -fsS --max-time 5 -H 'Cache-Control: no-cache' "https://www.anticipy.ai/api/app/state?x=$(date +%s)" 2>/dev/null | jq '{commit: .build.commit, sha: .release.sha256}' || echo null)
    LOCAL_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")
    ORIGIN_HEAD=$(git ls-remote origin refs/heads/main 2>/dev/null | awk '{print $1}')
    jq -n \
      --arg ts "$(ts)" \
      --arg engine_pid "${ENGINE_PID:-}" \
      --arg bridge_pid "${BRIDGE_PID:-}" \
      --arg chrome "$CHROME" \
      --argjson str "$STR_ALIVE" \
      --argjson ralph "$RALPH_ALIVE" \
      --argjson sup "$SUP_ALIVE" \
      --argjson breadth "$BREADTH" \
      --argjson green "$GATE_GREEN" \
      --argjson red "$GATE_RED" \
      --argjson live "$LIVE" \
      --arg local "$LOCAL_HEAD" \
      --arg origin "$ORIGIN_HEAD" \
      '{ts: $ts, engine_pid: $engine_pid, bridge_pid: $bridge_pid, chrome_9222: $chrome, strangers_alive: $str, ralph_alive: $ralph, supervisor_alive: $sup, breadth: $breadth, gates: {green: $green, red: $red}, live: $live, repo: {local: $local, origin: $origin}}' \
      > "$STATUS_FILE" 2>/dev/null || true
    sleep 30
  done
}

start_all() {
  loop_health     >> "$LOG_DIR/health_loop.log"     2>&1 &
  PID_HEALTH=$!
  loop_strangers  >> "$LOG_DIR/strangers_loop.log"  2>&1 &
  PID_STRANGERS=$!
  loop_v7_gates   >> "$LOG_DIR/v7_gates_loop.log"   2>&1 &
  PID_V7=$!
  loop_autocommit >> "$LOG_DIR/autocommit_loop.log" 2>&1 &
  PID_AC=$!
  loop_ralph_trillion >> "$LOG_DIR/ralph_trillion.log" 2>&1 &
  PID_TRIL=$!
  loop_status     >> "$LOG_DIR/status_loop.log"     2>&1 &
  PID_STATUS=$!
  log "started: health=$PID_HEALTH strangers=$PID_STRANGERS v7=$PID_V7 ac=$PID_AC trillion=$PID_TRIL status=$PID_STATUS"
}

start_all

trap 'log "supervisor exiting"; kill $PID_HEALTH $PID_STRANGERS $PID_V7 $PID_AC $PID_TRIL $PID_STATUS 2>/dev/null; rm -f "$PID_FILE"; exit 0' INT TERM EXIT

while [ ! -f "$STOP_FILE" ]; do
  for VAR in PID_HEALTH PID_STRANGERS PID_V7 PID_AC PID_TRIL PID_STATUS; do
    eval "PID=\$$VAR"
    if ! kill -0 "$PID" 2>/dev/null; then
      log "child $VAR pid=$PID died; restarting all"
      kill $PID_HEALTH $PID_STRANGERS $PID_V7 $PID_AC $PID_TRIL $PID_STATUS 2>/dev/null
      sleep 2
      start_all
      break
    fi
  done
  sleep 30
done

log "stop file detected"
kill $PID_HEALTH $PID_STRANGERS $PID_V7 $PID_AC $PID_TRIL $PID_STATUS 2>/dev/null
rm -f "$PID_FILE"
exit 0
