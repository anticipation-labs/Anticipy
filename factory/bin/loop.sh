#!/usr/bin/env bash
# The Factory loop. Each lap: build -> verify (mechanical) -> [judge] -> scoreboard ->
# keep/revert -> treadmill check -> spend record.
#
# Usage: loop.sh [--once] [--max-laps N] [--nightly] [--until HH:MM]
# Stop conditions: .halt, OPEN escalation, max laps, nightly window end.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
source factory/config/factory.conf
PY="engine/.venv/bin/python"
# The loop's own journal is untracked so git reset --hard on a reverted lap can't eat it.
# (Builders append to logs/journal.md inside their commits; that rides the keep/revert.)
JOURNAL="logs/factory/loop_journal.md"

MAX_LAPS=0; UNTIL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --once) MAX_LAPS=1; shift ;;
    --max-laps) MAX_LAPS="$2"; shift 2 ;;
    --nightly) UNTIL="0$NIGHTLY_STOP_HOUR:00"; shift ;;
    --until) UNTIL="$2"; shift 2 ;;
    *) echo "unknown arg $1"; exit 2 ;;
  esac
done
[[ "$MAX_LAPS" =~ ^[0-9]+$ ]] || { echo "--max-laps must be a non-negative integer"; exit 2; }

journal() { printf '\n- %s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$JOURNAL"; }
notify() { osascript -e "display notification \"$1\" with title \"Anticipy Factory\"" >/dev/null 2>&1 || true; }

# resolve the claude binary once so launchd/cron contexts can't lose it (ledger D1)
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
[[ -x "$CLAUDE_BIN" ]] || CLAUDE_BIN="$HOME/.local/bin/claude"
if [[ ! -x "$CLAUDE_BIN" && -z "${FACTORY_BUILD_CMD:-}" ]]; then
  journal "loop abort: claude binary not found (CLAUDE_BIN)"; notify "Factory: claude binary not found"; exit 1
fi
export CLAUDE_BIN

# ---- lock (stale if PID dead OR lock older than 24h — PID reuse guard, ledger D8) ----
if ! mkdir factory/.lock 2>/dev/null; then
  PID=$(cat factory/.lock/pid 2>/dev/null || echo "")
  LOCK_AGE=$(( $(date +%s) - $(stat -f %m factory/.lock 2>/dev/null || echo 0) ))
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null && [[ "$LOCK_AGE" -lt 86400 ]]; then
    echo "loop already running (pid $PID)"; exit 1
  fi
  rm -rf factory/.lock; mkdir factory/.lock
fi
echo $$ > factory/.lock/pid
trap 'rm -rf factory/.lock' EXIT

# ---- crash/orphan recovery (ledger A3): a marker means a lap died mid-flight ----
if [[ -f factory/.lap_in_progress ]]; then
  ORPHAN=$(cat factory/.lap_in_progress)
  ORPHAN_BASE=$(cat "logs/factory/laps/$ORPHAN/base" 2>/dev/null || echo "")
  if [[ -n "$ORPHAN_BASE" && ! -f "logs/factory/laps/$ORPHAN/gate_results.json" ]]; then
    if [[ "$(git rev-parse HEAD)" != "$ORPHAN_BASE" ]]; then
      git diff "$ORPHAN_BASE" HEAD > "logs/factory/laps/$ORPHAN/orphaned.patch" 2>/dev/null || true
      MEAS_TMP=$(mktemp -d)
      for MF in logs/factory/product_scoreboard.csv logs/factory/RATCHET.json logs/factory/FAILURE_MODES.md; do
        [[ -f "$MF" ]] && cp "$MF" "$MEAS_TMP/$(basename "$MF")"
      done
      git reset --hard "$ORPHAN_BASE" >/dev/null 2>&1 || true
      for MF in product_scoreboard.csv RATCHET.json FAILURE_MODES.md; do
        [[ -f "$MEAS_TMP/$MF" ]] && cp "$MEAS_TMP/$MF" "logs/factory/$MF"
      done
      rm -rf "$MEAS_TMP"
      journal "loop start: rolled back ORPHANED unverified lap $ORPHAN to ${ORPHAN_BASE:0:8} (patch kept, measurement preserved)"
    fi
    mkdir -p logs/factory/aborted
    git diff -- . ':!logs' > "logs/factory/aborted/$(date -u +%Y%m%dT%H%M%SZ)-$ORPHAN.patch" 2>/dev/null || true
    git checkout -- . ':!logs' 2>/dev/null || true
  fi
  rm -f factory/.lap_in_progress
fi

# ---- dirty PRODUCT tree with NO crashed lap = foreman WIP: refuse, never destroy (ledger A1) ----
if [[ -n "$(git status --porcelain -- . ':!logs' ':!PENDING_FOR_OMAR.md' | grep -vE '^\?\?' || true)" ]]; then
  journal "loop abort: uncommitted product changes present (foreman WIP?) — refusing to run"
  notify "Factory: refused to start over uncommitted changes"
  exit 1
fi

# ---- hygiene: prune old persona runs (7d), sweep stale eval/gate engines (ledger D4, D10) ----
find logs/factory/runs -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true
for P in $(seq 8801 8816) 8899; do
  PIDS=$(lsof -ti tcp:$P 2>/dev/null || true)
  [[ -n "$PIDS" ]] && { echo "$PIDS" | xargs kill 2>/dev/null || true; journal "loop start: killed stale engine on :$P"; }
done

LAPS=0
while true; do
  # ---- stop conditions ----
  [[ -f factory/.halt ]] && { journal "loop stop: .halt present"; break; }
  if [[ -f factory/ESCALATION.md ]] && grep -q 'STATUS: OPEN' factory/ESCALATION.md; then
    journal "loop stop: ESCALATION OPEN — foreman must resolve"; break
  fi
  if [[ "$MAX_LAPS" -gt 0 && "$LAPS" -ge "$MAX_LAPS" ]]; then break; fi
  if [[ -n "$UNTIL" ]]; then
    NOW=$(date +%H:%M)
    # stop when we reach the morning boundary (window assumed to cross midnight)
    if [[ "$NOW" < "12:00" && ! "$NOW" < "$UNTIL" ]]; then
      journal "loop stop: nightly window ended ($UNTIL)"; break
    fi
  fi

  LAP=$(date -u +%Y%m%dT%H%M%SZ)
  LAPDIR="logs/factory/laps/$LAP"
  mkdir -p "$LAPDIR"
  BEFORE=$(git rev-parse HEAD)
  echo "$BEFORE" > "$LAPDIR/base"            # orphan-recovery anchor (ledger A3)
  echo "$LAP" > factory/.lap_in_progress

  # ---- budget tier ----
  if "$PY" factory/bin/spend.py check --kind build >/dev/null 2>&1; then
    TIER=FULL
  else
    TIER=FREE
  fi
  export FACTORY_BUDGET_MODE="$TIER"
  journal "lap $LAP starting (tier=$TIER, base=${BEFORE:0:8})"

  # ---- build ----
  bash factory/bin/build_lap.sh "$LAP" "$TIER"
  BUILD_RC=$?
  AFTER=$(git rev-parse HEAD)
  LIMIT_HIT=$("$PY" - "$LAPDIR/build.json" <<'PY'
import json, sys
try:
    obj = json.load(open(sys.argv[1]))
except Exception:
    obj = {}
result = str(obj.get("result", "")).lower()
is_limit = obj.get("api_error_status") == 429 or "session limit" in result
print("true" if is_limit else "false")
PY
  )
  # builder may leave uncommitted PRODUCT edits on timeout/crash — preserve then drop them
  # (logs/ and PENDING_FOR_OMAR.md are legitimate lap outputs; they stay)
  if [[ -n "$(git status --porcelain -- . ':!logs' ':!PENDING_FOR_OMAR.md' | grep -vE '^\?\?' || true)" ]]; then
    git diff -- . ':!logs' ':!PENDING_FOR_OMAR.md' > "$LAPDIR/uncommitted.patch" || true
    git checkout -- . ':!logs' ':!PENDING_FOR_OMAR.md' 2>/dev/null || true
  fi
  if [[ "$LIMIT_HIT" == "true" ]]; then
    if [[ "$AFTER" != "$BEFORE" ]]; then
      git diff "$BEFORE" "$AFTER" > "$LAPDIR/reverted.patch" || true
      git reset --hard "$BEFORE" >/dev/null
    fi
    cat > "$LAPDIR/skipped.json" <<EOF
{"lap":"$LAP","status":"SKIPPED_LIMIT","reason":"builder session limit / 429","build_rc":$BUILD_RC}
EOF
    journal "lap $LAP skipped: SKIPPED_LIMIT (builder session limit/429; no score, no treadmill)"
    rm -f factory/.lap_in_progress
    LAPS=$((LAPS + 1))
    sleep "${SESSION_LIMIT_BACKOFF_SECONDS:-180}"
    continue
  fi

  # ---- mechanical verify (wall-capped; a hung gate must not strand the lap, ledger D6) ----
  GATE=FAIL
  ( sleep 3600; pkill -P $$ -f verify_gate 2>/dev/null ) & VG_WATCHDOG=$!
  if bash factory/bin/verify_gate.sh "$LAP" "$BEFORE"; then GATE=PASS; fi
  kill "$VG_WATCHDOG" 2>/dev/null; wait "$VG_WATCHDOG" 2>/dev/null
  # a failed build that still committed must never be kept (ledger D5)
  if [[ "${BUILD_RC:-127}" -ne 0 && "$AFTER" != "$BEFORE" ]]; then
    GATE=FAIL
    journal "lap $LAP: build rc=$BUILD_RC with commits — forcing revert"
  fi

  # ---- judge (selfcheck weekly; full judge on phase-close candidates, budget allowing) ----
  JUDGE_RAN=false
  LAST_SC=$(ls -1 logs/factory/laps/*/selfcheck.md 2>/dev/null | tail -1)
  SC_DUE=true
  if [[ -n "$LAST_SC" ]]; then
    AGE_DAYS=$(( ( $(date +%s) - $(stat -f %m "$LAST_SC") ) / 86400 ))
    [[ "$AGE_DAYS" -lt "${JUDGE_SELFCHECK_EVERY_DAYS:-7}" ]] && SC_DUE=false
  fi
  PHASE_CLOSED=$("$PY" -c "import json;print(json.dumps(json.load(open('$LAPDIR/gate_results.json')).get('phase_gate_passed', False)))" 2>/dev/null || echo false)
  JUDGE_BLOCK=false
  if [[ "$TIER" == "FULL" ]]; then
    if [[ "$SC_DUE" == "true" ]]; then
      bash factory/bin/judge_lap.sh "$LAP" --self-check || journal "lap $LAP: judge selfcheck errored"
      if [[ -f "$LAPDIR/selfcheck.md" ]] && ! grep -qi 'FAKE' "$LAPDIR/selfcheck.md"; then
        echo '{"verdict": "JUDGE_BROKEN"}' > "$LAPDIR/judge.json"
        journal "lap $LAP: JUDGE_BROKEN — selfcheck failed to catch the planted fake"
        JUDGE_BLOCK=true
      fi
    fi
    if [[ "$PHASE_CLOSED" == "true" && "$JUDGE_BLOCK" == "false" ]]; then
      if "$PY" factory/bin/spend.py check --kind judge >/dev/null 2>&1; then
        if ! bash factory/bin/judge_lap.sh "$LAP"; then
          journal "lap $LAP: judge errored — phase closure blocked"
          echo '{"verdict": "JUDGE_ERROR", "reason": "judge_lap.sh failed or hit an external limit before writing a trusted verdict"}' > "$LAPDIR/judge.json"
        elif [[ ! -f "$LAPDIR/judge.json" ]]; then
          journal "lap $LAP: judge wrote no judge.json — phase closure blocked"
          echo '{"verdict": "JUDGE_ERROR", "reason": "judge_lap.sh exited without judge.json"}' > "$LAPDIR/judge.json"
        fi
        JUDGE_RAN=true
      else
        journal "lap $LAP: judge budget unavailable — phase closure blocked"
        echo '{"verdict": "JUDGE_SKIPPED", "reason": "judge budget unavailable for phase-close candidate"}' > "$LAPDIR/judge.json"
      fi
    fi
  fi

  # ---- keep / revert ----
  VETO=false
  JUDGE_VERDICT=$("$PY" - "$LAPDIR/judge.json" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("verdict", "NA"))
except Exception:
    print("NA")
PY
  )
  if [[ -f "$LAPDIR/judge.json" ]] && grep -qE '"verdict":\s*"(FAKE|VETO|JUDGE_BROKEN|JUDGE_ERROR|JUDGE_SKIPPED)"' "$LAPDIR/judge.json"; then
    VETO=true
  fi
  if [[ "$PHASE_CLOSED" == "true" && "$JUDGE_VERDICT" != "REAL" ]]; then
    VETO=true
    journal "lap $LAP: phase close blocked until judge verdict REAL (have $JUDGE_VERDICT)"
  fi
  if [[ "$GATE" == "PASS" && "$VETO" == "false" ]]; then
    KEPT=true
  else
    KEPT=false
    if [[ "$AFTER" != "$BEFORE" ]]; then
      git diff "$BEFORE" "$AFTER" > "$LAPDIR/reverted.patch" || true
      # measurement state is tracked but updated between commits — reset --hard
      # rolled it back once and corrupted the books (ledger C14). Snapshot/restore.
      MEAS_TMP=$(mktemp -d)
      for MF in logs/factory/product_scoreboard.csv logs/factory/RATCHET.json logs/factory/FAILURE_MODES.md; do
        [[ -f "$MF" ]] && cp "$MF" "$MEAS_TMP/$(basename "$MF")"
      done
      git reset --hard "$BEFORE" >/dev/null
      for MF in product_scoreboard.csv RATCHET.json FAILURE_MODES.md; do
        [[ -f "$MEAS_TMP/$MF" ]] && cp "$MEAS_TMP/$MF" "logs/factory/$MF"
      done
      rm -rf "$MEAS_TMP"
    fi
  fi

  # ---- scoreboard (its failure = measurement broke = stop the line, ledger D9/C5) ----
  if ! "$PY" factory/bin/scoreboard.py --lap "$LAP" --kept "$KEPT" > "$LAPDIR/scoreboard.out" 2>&1; then
    journal "lap $LAP: SCOREBOARD FAILED — halting the line (measurement integrity)"
    notify "Factory halted: scoreboard failure on lap $LAP"
    touch factory/.halt
    rm -f factory/.lap_in_progress
    break
  fi
  "$PY" factory/bin/spend.py record --lap "$LAP" \
      --build-json "$LAPDIR/build.json" \
      $([[ "$JUDGE_RAN" == "true" ]] && echo --judge-json "$LAPDIR/judge.stream.jsonl") \
      >/dev/null 2>&1 || journal "lap $LAP: spend record FAILED (non-fatal)"
  rm -f factory/.lap_in_progress
  journal "lap $LAP done: build_rc=$BUILD_RC gate=$GATE kept=$KEPT $(grep -o '"metric_moved": "[^"]*"' "$LAPDIR/scoreboard.out" | head -1 || true)"

  if ! "$PY" factory/bin/treadmill.py; then
    journal "TREADMILL HALT after lap $LAP — ESCALATION.md written, loop stopping"
    break
  fi

  LAPS=$((LAPS + 1))
done

# ---- off-Mac-disaster insurance: bundle backup, keep last 7 (ledger A4) ----
mkdir -p "$HOME/Anticipy-backups"
git bundle create "$HOME/Anticipy-backups/factory-build-$(date -u +%Y%m%dT%H%M%SZ).bundle" factory/build >/dev/null 2>&1 \
  && ls -1t "$HOME/Anticipy-backups"/factory-build-*.bundle 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true
journal "loop exited after $LAPS lap(s)"
