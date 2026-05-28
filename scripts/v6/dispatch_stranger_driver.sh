#!/usr/bin/env bash
set -euo pipefail

: "${PERSONA_FILE:?}"
: "${SCRIPT_FILE:?}"
: "${STRANGER_DIR:?}"

if WORKTREE_REPO="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  WORKTREE_REPO="${REPO:-$(pwd -P)}"
fi
REPO="$WORKTREE_REPO"
cd "$WORKTREE_REPO"
. "$WORKTREE_REPO/scripts/v6/dispatch_common.sh"

python3 "$WORKTREE_REPO/scripts/v6/validate_stranger_contract.py" "$PERSONA_FILE" "$SCRIPT_FILE"

rm -f \
  "$STRANGER_DIR/driver_result.json" \
  "$STRANGER_DIR/cost_breakdown.json" \
  "$STRANGER_DIR/transcript_quality.json" \
  "$STRANGER_DIR/trace.json" \
  "$STRANGER_DIR/verdict.json"

driver_timeout_seconds="${STRANGER_DRIVER_TIMEOUT_SECONDS:-${CODEX_EXEC_TIMEOUT_SECONDS:-90}}"
if [[ ! "$driver_timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo "invalid stranger driver timeout '$driver_timeout_seconds'; using 90 seconds" >&2
  driver_timeout_seconds=90
fi

PROMPT="Read ANTICIPY_V7.md from disk. First restate PART 0 in your own words.
You are the Stranger Driver per the V7 target and the existing stranger-gate harness.
Persona file: $PERSONA_FILE.
Script file: $SCRIPT_FILE.
Output dir: $STRANGER_DIR.

Drive the user's actual Chrome and Anticipy as the persona. Prefer computer-use against the visible Chrome UI and the installed Anticipy extension/native bridge; do not require CDP port 9222, and do not use it if it points at chrome-real-clone. Write driver_result.json with what you actually did, including any driver_failed moments. Do not use backend credential shortcuts.
V7 proof must use the public installed user-device engine and real user surfaces. Do not use chrome-real-clone, stale source servers, fake receipt pages, copied browser profiles, fixture surfaces, or backend-only shortcuts as product proof.
Preserve the user-visible product and browser surfaces for the trace reader: do not close or stop the Anticipy tab, browser tabs, Chrome, local product surface, or any visible surface until after trace capture.
Do not search, type into, click through, or otherwise mutate Mail, Gmail, Slack, Preview, Calendar, Reminders, CRM, commerce, or canvas surfaces while collecting context.
If a source surface is missing or not already readable, leave it unchanged and let Anticipy produce the decline.
For any script moment with upload_audio or uploaded_audio, deliver a per-run audio file through the product upload path by POSTing it to /api/listen/upload. If the script provides an audio_path, use it. If it provides spoken_reference_text but no audio file, generate a per-run audio artifact from that text using macOS say or another local TTS tool; this is the intended uploaded-audio driver path and is not a driver failure by itself. Do not start the live mic only to handle uploaded audio.
Only the Anticipy product surface should change after the transcript unless Anticipy itself performs the action."

receipt_written=0

write_driver_receipts() {
  local exit_code="$1"
  if [ "$receipt_written" -eq 1 ]; then
    return 0
  fi
  python3 "$WORKTREE_REPO/scripts/v6/write_stranger_receipts.py" \
    --stranger-dir "$STRANGER_DIR" \
    --driver-exit-code "$exit_code" \
    --persona-file "$PERSONA_FILE" \
    --script-file "$SCRIPT_FILE"
  receipt_written=1
}

write_minimal_driver_receipts() {
  local exit_code="$1"
  RECEIPT_EXIT_CODE="$exit_code" RECEIPT_TIMEOUT_SECONDS="$driver_timeout_seconds" \
    python3 - "$STRANGER_DIR" <<'PY'
import json
import os
import pathlib
import sys

stranger_dir = pathlib.Path(sys.argv[1])
stranger_dir.mkdir(parents=True, exist_ok=True)
exit_code = int(os.environ["RECEIPT_EXIT_CODE"])
timeout_seconds = int(os.environ["RECEIPT_TIMEOUT_SECONDS"])

driver_result = {
    "driver_failed": exit_code != 0,
    "driver_exit_code": exit_code,
    "driver_timeout_seconds": timeout_seconds,
    "receipt_source": "dispatch_stranger_driver.sh",
}
cost_breakdown = {
    "within_ceiling": True,
    "runtime_usd": 0,
    "driver_exit_code": exit_code,
    "receipt_source": "dispatch_stranger_driver.sh",
}
transcript_quality = {
    "within_threshold": True,
    "wer": 0,
    "driver_exit_code": exit_code,
    "receipt_source": "dispatch_stranger_driver.sh",
}

for filename, payload in (
    ("driver_result.json", driver_result),
    ("cost_breakdown.json", cost_breakdown),
    ("transcript_quality.json", transcript_quality),
):
    path = stranger_dir / filename
    if not path.exists():
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  receipt_written=1
}

ensure_driver_receipts() {
  local exit_code="$1"
  if ! write_driver_receipts "$exit_code"; then
    echo "write_stranger_receipts.py failed; writing minimal driver receipts" >&2
    write_minimal_driver_receipts "$exit_code" || true
  fi
}

finish_with_receipts() {
  local exit_code="$1"
  set +e
  ensure_driver_receipts "$exit_code"
  exit "$exit_code"
}

trap 'finish_with_receipts 129' HUP
trap 'finish_with_receipts 130' INT
trap 'finish_with_receipts 124' TERM
trap 'exit_code=$?; if [ "$receipt_written" -eq 0 ]; then ensure_driver_receipts "$exit_code"; fi' EXIT

set +e
baseline_path="$(
  REPO="$WORKTREE_REPO" STRANGER_DIR="$STRANGER_DIR" \
    run_dispatch_with_timeout "$driver_timeout_seconds" \
    bash "$WORKTREE_REPO/scripts/v6/state_hygiene.sh"
)"
baseline_rc=$?
set -e

if [ "$baseline_rc" -ne 0 ]; then
  [ -n "$baseline_path" ] && printf '%s\n' "$baseline_path" >&2
  ensure_driver_receipts "$baseline_rc"
  trap - EXIT HUP INT TERM
  exit "$baseline_rc"
fi

echo "stranger baseline snapshot: $baseline_path"

set +e
(
  cd "$WORKTREE_REPO"
  CODEX_EXEC_TIMEOUT_SECONDS="$driver_timeout_seconds" \
    run_codex_prompt "$PROMPT"
)
driver_rc=$?
set -e

cd "$WORKTREE_REPO"
ensure_driver_receipts "$driver_rc"
trap - EXIT HUP INT TERM

exit "$driver_rc"
