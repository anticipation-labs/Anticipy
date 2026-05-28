#!/usr/bin/env bash
# write_status.sh — produce state/STATUS.md per cycle.
set -uo pipefail

CYCLE=${1:?cycle required}
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CYCLE_DIR="state/cycle-$CYCLE"

# Tally verdict counts
if [ -f "$CYCLE_DIR/judge_verdict.json" ]; then
  M=$(jq -r '[.verdicts[] | select(.decision == "merge")] | length' "$CYCLE_DIR/judge_verdict.json")
  R=$(jq -r '[.verdicts[] | select(.decision == "reject")] | length' "$CYCLE_DIR/judge_verdict.json")
  E=$(jq -r '[.verdicts[] | select(.decision == "escalate")] | length' "$CYCLE_DIR/judge_verdict.json")
else
  M="?"; R="?"; E="?"
fi

# Last regression
if [ -L state/regression-latest ]; then
  LATEST=$(readlink state/regression-latest)
  if [ -f "state/$LATEST/PASS" ]; then
    REGRESSION="PASS"
  elif [ -f "state/$LATEST/FAIL" ]; then
    REGRESSION="FAIL ($(wc -l < state/$LATEST/fails.log) red)"
  else
    REGRESSION="?"
  fi
else
  REGRESSION="never run"
fi

# Last MP3 eval
if [ -L state/mp3_eval/latest ]; then
  MP3_RUN=$(readlink state/mp3_eval/latest)
  if [ -f "state/mp3_eval/$MP3_RUN/verdict.json" ]; then
    MP3P=$(jq -r '.pass' "state/mp3_eval/$MP3_RUN/verdict.json")
    MP3G=$(jq -r '.overall_grade' "state/mp3_eval/$MP3_RUN/verdict.json")
    MP3="pass=$MP3P grade=$MP3G ($MP3_RUN)"
  else
    MP3="run in progress"
  fi
else
  MP3="never run"
fi

# Decisions
PENDING_DECISIONS=0
[ -f state/decisions/queue.md ] && PENDING_DECISIONS=$(grep -c "^##" state/decisions/queue.md || echo 0)

# Recent commits
COMMITS=$(git log -10 --pretty=format:"- %s" 2>/dev/null || echo "(no commits)")

cat > state/STATUS.md <<EOF
# Anticipy autonomous build — STATUS

Updated: $TS
Cycle: $CYCLE

## This cycle
- Workers: $M merged, $R rejected, $E escalated

## Regression suite (deterministic, no LLM)
$REGRESSION

## MP3 held-out eval (Omar's real day)
$MP3

## Pending decisions in state/decisions/queue.md
$PENDING_DECISIONS items

## Last 10 commits
$COMMITS

---

Read this whenever. Override decisions by editing \`state/decisions/queue.md\`. The loop is autonomous.

If the loop has gone wrong: check for \`state/STUCK.md\`, \`state/SETUP_BROKEN.md\`, or \`state/COMPLETE.md\`.
EOF
