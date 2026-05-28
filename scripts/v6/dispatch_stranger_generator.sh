#!/usr/bin/env bash
set -euo pipefail

: "${CYCLE:?}"
: "${CYCLE_DIR:?}"

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"
. scripts/v6/dispatch_common.sh

PROMPT="Read ANTICIPY_V7.md from disk. First restate PART 0 in your own words.
You are the Stranger Generator per the V7 target and the existing stranger-gate harness.

Generate one fresh stranger persona and one script. Enforce rolling hard-category breadth using state/stranger_breadth.json if it exists. Create a new UUID directory under state/strangers/. Write persona.json and script.json there. Use real user surfaces for hard categories, not local stand-ins or generic browser notes. Do not reuse existing personas. Do not create fixed fixture libraries.
If state/last_v6_transcript_audit.json exists and the verdict is no_data or fail, the generated script must force real audio ASR coverage on the same post-ASR pipeline using uploaded audio: include a moment with kind upload_audio and input_fidelity uploaded_audio. In that case do not make the primary user input transcript_paste, paste-only, live_mic, or microphone permission dependent.
For V7, prefer scripts that expose input-mode and surface proof gaps: MP3/audio upload, transcript paste/upload, computer microphone, external microphone selection, real Chrome/user surface, no cloned Chrome, no fake receipts, and public installed user-device engine behavior."

run_codex_prompt "$PROMPT"
VALIDATOR_ARGS=(--latest state/strangers)
if [[ -f state/last_v6_transcript_audit.json ]]; then
  VALIDATOR_ARGS=(--transcript-audit state/last_v6_transcript_audit.json "${VALIDATOR_ARGS[@]}")
fi
python3 scripts/v6/validate_stranger_contract.py "${VALIDATOR_ARGS[@]}"
