#!/usr/bin/env bash
# Fresh-context autopilot loop. Runs until milestones are done, a full human gate
# blocks every path, or AUTOPILOT_MAX_LAPS is reached for a smoke run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

mkdir -p logs/trace logs/verdicts logs/codex
MAX_LAPS="${AUTOPILOT_MAX_LAPS:-0}"
COUNT=0

append_journal() {
  local text="$1"
  mkdir -p logs
  printf '%s %s\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$text" >> logs/journal.md
}

while true; do
  if [[ -f logs/last_lap.md ]] && grep -q '^ALL_MILESTONES_DONE: true' logs/last_lap.md; then
    append_journal "Autopilot stopped because logs/last_lap.md says all milestones are done."
    break
  fi

  if [[ -f PENDING_FOR_OMAR.md ]] && grep -q '^BLOCKS_ALL: true' PENDING_FOR_OMAR.md; then
    append_journal "Autopilot stopped because PENDING_FOR_OMAR.md has BLOCKS_ALL: true."
    break
  fi

  if [[ "$MAX_LAPS" != "0" && "$COUNT" -ge "$MAX_LAPS" ]]; then
    append_journal "Autopilot smoke loop stopped after AUTOPILOT_MAX_LAPS=$MAX_LAPS."
    break
  fi

  LAP="$(date -u +%Y%m%dT%H%M%SZ)"
  BEFORE="$(git rev-parse HEAD)"
  append_journal "Lap $LAP started. Base commit $BEFORE."

  AUTOPILOT_LAP="$LAP" autopilot/build_lap
  AFTER="$(git rev-parse HEAD)"
  AUTOPILOT_LAP="$LAP" autopilot/judge_lap

  VERDICT_FILE="logs/verdicts/${LAP}.md"
  if [[ -f "$VERDICT_FILE" ]] && grep -qi '^Verdict: REAL' "$VERDICT_FILE"; then
    append_journal "Lap $LAP kept. Judge verdict REAL."
  else
    append_journal "Lap $LAP was not proven REAL. See $VERDICT_FILE."
    if [[ "$AFTER" != "$BEFORE" ]]; then
      git revert --no-edit "$AFTER"
      append_journal "Lap $LAP commit $AFTER reverted by gate."
    fi
  fi

  COUNT=$((COUNT + 1))
done
