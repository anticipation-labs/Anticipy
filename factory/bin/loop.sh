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

journal() { printf '\n- %s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$JOURNAL"; }

# ---- lock ----
if ! mkdir factory/.lock 2>/dev/null; then
  PID=$(cat factory/.lock/pid 2>/dev/null || echo "")
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "loop already running (pid $PID)"; exit 1
  fi
  rm -rf factory/.lock; mkdir factory/.lock
fi
echo $$ > factory/.lock/pid
trap 'rm -rf factory/.lock' EXIT

# ---- crash recovery: stash any dirty PRODUCT tree from a dead lap (logs are ours) ----
if [[ -n "$(git status --porcelain -- . ':!logs' ':!PENDING_FOR_OMAR.md' | grep -vE '^\?\?' || true)" ]]; then
  mkdir -p logs/factory/aborted
  git diff -- . ':!logs' > "logs/factory/aborted/$(date -u +%Y%m%dT%H%M%SZ).patch" || true
  git checkout -- . ':!logs' 2>/dev/null || true
  journal "loop start: recovered dirty product tree to logs/factory/aborted/ and reset"
fi

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
  # builder may leave uncommitted PRODUCT edits on timeout/crash — preserve then drop them
  # (logs/ and PENDING_FOR_OMAR.md are legitimate lap outputs; they stay)
  if [[ -n "$(git status --porcelain -- . ':!logs' ':!PENDING_FOR_OMAR.md' | grep -vE '^\?\?' || true)" ]]; then
    git diff -- . ':!logs' ':!PENDING_FOR_OMAR.md' > "$LAPDIR/uncommitted.patch" || true
    git checkout -- . ':!logs' ':!PENDING_FOR_OMAR.md' 2>/dev/null || true
  fi

  # ---- mechanical verify ----
  if bash factory/bin/verify_gate.sh "$LAP" "$BEFORE"; then GATE=PASS; else GATE=FAIL; fi

  # ---- judge (selfcheck weekly; full judge on phase-close candidates, budget allowing) ----
  JUDGE_RAN=false
  LAST_SC=$(ls -1 logs/factory/laps/*/selfcheck.md 2>/dev/null | tail -1)
  SC_DUE=true
  if [[ -n "$LAST_SC" ]]; then
    AGE_DAYS=$(( ( $(date +%s) - $(stat -f %m "$LAST_SC") ) / 86400 ))
    [[ "$AGE_DAYS" -lt "${JUDGE_SELFCHECK_EVERY_DAYS:-7}" ]] && SC_DUE=false
  fi
  PHASE_CLOSED=$("$PY" -c "import json;print(json.load(open('$LAPDIR/gate_results.json')).get('phase_gate_passed', False))" 2>/dev/null || echo False)
  if [[ "$TIER" == "FULL" ]]; then
    if [[ "$SC_DUE" == "true" ]]; then
      bash factory/bin/judge_lap.sh "$LAP" --self-check || journal "lap $LAP: judge selfcheck errored"
      if [[ -f "$LAPDIR/selfcheck.md" ]] && ! grep -qi 'FAKE' "$LAPDIR/selfcheck.md"; then
        echo '{"verdict": "JUDGE_BROKEN"}' > "$LAPDIR/judge.json"
        journal "lap $LAP: JUDGE_BROKEN — selfcheck failed to catch the planted fake"
      fi
    fi
    if [[ "$PHASE_CLOSED" == "True" ]] && "$PY" factory/bin/spend.py check --kind judge >/dev/null 2>&1; then
      bash factory/bin/judge_lap.sh "$LAP" || journal "lap $LAP: judge errored"
      JUDGE_RAN=true
    fi
  fi

  # ---- keep / revert ----
  VETO=false
  if [[ -f "$LAPDIR/judge.json" ]] && grep -qE '"verdict":\s*"(FAKE|VETO)"' "$LAPDIR/judge.json"; then
    VETO=true
  fi
  if [[ "$GATE" == "PASS" && "$VETO" == "false" ]]; then
    KEPT=true
  else
    KEPT=false
    if [[ "$AFTER" != "$BEFORE" ]]; then
      git diff "$BEFORE" "$AFTER" > "$LAPDIR/reverted.patch" || true
      git reset --hard "$BEFORE" >/dev/null
    fi
  fi

  # ---- scoreboard + treadmill + spend ----
  "$PY" factory/bin/scoreboard.py --lap "$LAP" --kept "$KEPT" > "$LAPDIR/scoreboard.out" 2>&1 || true
  "$PY" factory/bin/spend.py record --lap "$LAP" \
      --build-json "$LAPDIR/build.json" \
      $([[ "$JUDGE_RAN" == "true" ]] && echo --judge-json "$LAPDIR/judge.stream.jsonl") \
      >/dev/null 2>&1 || true
  journal "lap $LAP done: build_rc=$BUILD_RC gate=$GATE kept=$KEPT $(grep -o '"metric_moved": "[^"]*"' "$LAPDIR/scoreboard.out" | head -1 || true)"

  if ! "$PY" factory/bin/treadmill.py; then
    journal "TREADMILL HALT after lap $LAP — ESCALATION.md written, loop stopping"
    break
  fi

  LAPS=$((LAPS + 1))
done
journal "loop exited after $LAPS lap(s)"
