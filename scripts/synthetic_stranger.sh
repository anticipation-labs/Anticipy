#!/usr/bin/env bash
# synthetic_stranger.sh — the trillion-dollar-investor simulation
#
# Codex computer use opens a fresh Chrome incognito, signs up, installs,
# onboards, uses the product as a stranger persona, records video.
#
# This is the ONLY way to verify the trillion-dollar-stranger bar in docs/DONE.md.
# It runs once per cycle at peak, once per 6h steady-state.
#
# Output: video at state/stranger-runs/<timestamp>/recording.mp4
#         report at state/stranger-runs/<timestamp>/report.md
#         verdict at state/stranger-runs/<timestamp>/verdict.json
#
# Verdict is graded by a SECOND independent model (different OpenRouter provider)
# reading the report. Both must agree the experience was flawless.

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"

source scripts/load_env.sh
load_anticipy_env

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="state/stranger-runs/$RUN_ID"
mkdir -p "$RUN_DIR"

log() { echo "[stranger $RUN_ID] $*"; }

# Step 1: pick a persona from verifier/personas/
PERSONA=$(ls verifier/personas/*.json | shuf -n 1)
cp "$PERSONA" "$RUN_DIR/persona.json"
log "Persona: $PERSONA"

# Step 2: dispatch Codex computer use with explicit instructions
# This invocation uses Codex CLI's --computer-use flag. The agent is given
# the persona and the journey doc, and told to act as a stranger.
log "Dispatching Codex computer-use session."

codex run \
  --computer-use \
  --record "$RUN_DIR/recording.mp4" \
  --output "$RUN_DIR/transcript.txt" \
  --prompt-file scripts/prompts/stranger_prompt.md \
  --persona "$RUN_DIR/persona.json" \
  --max-minutes 20 \
  > "$RUN_DIR/codex.log" 2>&1 || {
    log "Codex session failed or timed out. See $RUN_DIR/codex.log"
    echo '{"verdict": "fail", "reason": "codex_session_failed"}' > "$RUN_DIR/verdict.json"
    exit 1
  }

# Step 3: Codex writes its own report at $RUN_DIR/report.md per its prompt
if [ ! -f "$RUN_DIR/report.md" ]; then
  log "Codex did not produce a report. Failing."
  echo '{"verdict": "fail", "reason": "no_report"}' > "$RUN_DIR/verdict.json"
  exit 1
fi

# Step 4: second independent grader reads the report
log "Dispatching independent grader."

python3 scripts/grade_stranger_run.py \
  --report "$RUN_DIR/report.md" \
  --done-doc docs/DONE.md \
  --output "$RUN_DIR/verdict.json"

# Step 5: parse verdict, exit accordingly
VERDICT=$(python3 -c "import json; print(json.load(open('$RUN_DIR/verdict.json'))['verdict'])")
if [ "$VERDICT" = "pass" ]; then
  log "Stranger run PASSED."
  exit 0
else
  log "Stranger run FAILED. See $RUN_DIR/verdict.json for reasons."
  exit 1
fi
