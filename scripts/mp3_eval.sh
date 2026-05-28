#!/usr/bin/env bash
# mp3_eval.sh — held-out evaluation against Omar's real 4-hour MP3.
#
# This is the trump card. The MP3 is real data the engine has never seen and never trains on.
# A fresh Codex sub-session grades the engine's output against the transcript per
# roles/mp3_evaluator.md. The evaluator has no awareness of the engine internals.

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"

run_bounded() {
  local seconds="$1"
  shift
  if [ -f "$REPO/scripts/v6/run_with_timeout.py" ]; then
    python3 "$REPO/scripts/v6/run_with_timeout.py" "$seconds" "$@"
  else
    perl -e 'alarm shift; exec @ARGV' "$seconds" "$@"
  fi
}

write_json_failure() {
  local path="$1"
  local reason="$2"
  local detail="${3:-}"
  jq -n \
    --arg reason "$reason" \
    --arg detail "$detail" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{pass:false, overall_grade:"F", reason:$reason, detail:$detail, written_at:$ts}' \
    > "$path"
}

if [ -f scripts/load_env.sh ]; then
  # shellcheck disable=SC1091
  . scripts/load_env.sh
  load_anticipy_env
fi

MP3="${MP3:-$HOME/Downloads/2026-05-21_08_11_04.mp3}"
if [ ! -f "$MP3" ]; then
  echo "MP3 not found at $MP3. Writing decision item."
  mkdir -p state/decisions
  cat >> state/decisions/queue.md <<EOF

## $(date -u +%Y-%m-%dT%H:%M:%SZ): MP3 eval blocked
Held-out MP3 not found at $MP3.
Default: skip mp3_eval until file appears. Loop continues.
EOF
  exit 2
fi

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
EVAL_DIR="state/mp3_eval/$RUN_ID"
mkdir -p "$EVAL_DIR"

# 1. Transcribe if we don't already have a cached transcript for this MP3.
MP3_HASH=$(shasum -a 256 "$MP3" | awk '{print $1}' | head -c 16)
TRANSCRIPT_CACHE="state/mp3_eval/cache-$MP3_HASH.txt"

if [ ! -f "$TRANSCRIPT_CACHE" ]; then
  echo "Transcribing MP3 (this happens once per unique MP3)."
  # parakeet-mlx is the local transcription model from FROZEN.md. Current
  # parakeet-mlx takes audio paths as positional args and writes files through
  # --output-dir/--output-format; older transcript subcommands are invalid.
  parakeet_bin_usable() {
    local bin="$1"
    local first_line=""
    local py=""
    [ -x "$bin" ] || return 1
    IFS= read -r first_line < "$bin" || first_line=""
    if [[ "$first_line" == '#!'* ]]; then
      py="${first_line#\#!}"
      py="${py%% *}"
      [ -x "$py" ] || return 1
      "$py" -c 'import lzma, parakeet_mlx' >/dev/null 2>&1
      return $?
    fi
    "$bin" --help >/dev/null 2>&1
  }

  choose_parakeet_bin() {
    local found=""
    for cand in \
      "state/mp3_eval/parakeet-venv/bin/parakeet-mlx" \
      "engine/.venv/bin/parakeet-mlx"; do
      if parakeet_bin_usable "$cand"; then
        printf '%s\n' "$cand"
        return 0
      fi
    done
    found="$(command -v parakeet-mlx 2>/dev/null || true)"
    if [ -n "$found" ] && parakeet_bin_usable "$found"; then
      printf '%s\n' "$found"
      return 0
    fi
    return 1
  }

  python_with_lzma() {
    for py in \
      "$HOME/.pyenv/versions/3.11.12/bin/python3" \
      "/usr/local/bin/python3" \
      "/opt/homebrew/bin/python3" \
      "$(command -v python3 2>/dev/null || true)"; do
      [ -n "$py" ] || continue
      [ -x "$py" ] || continue
      if "$py" -c 'import lzma' >/dev/null 2>&1; then
        printf '%s\n' "$py"
        return 0
      fi
    done
    return 1
  }

  ensure_scoped_parakeet_venv() {
    local venv="state/mp3_eval/parakeet-venv"
    local py=""
    if parakeet_bin_usable "$venv/bin/parakeet-mlx"; then
      return 0
    fi
    py="$(python_with_lzma || true)"
    if [ -z "$py" ]; then
      return 1
    fi
    rm -rf "$venv"
    "$py" -m venv "$venv"
    "$venv/bin/python" -m pip install --upgrade pip >/dev/null
    "$venv/bin/python" -m pip install "parakeet-mlx==0.5.1" >/dev/null
    parakeet_bin_usable "$venv/bin/parakeet-mlx"
  }

  PARAKEET_BIN="${PARAKEET_BIN:-}"
  if [ -n "$PARAKEET_BIN" ] && ! parakeet_bin_usable "$PARAKEET_BIN"; then
    echo "PARAKEET_BIN is not usable or its Python cannot import lzma: $PARAKEET_BIN"
    exit 1
  fi
  if [ -z "$PARAKEET_BIN" ]; then
    PARAKEET_BIN="$(choose_parakeet_bin || true)"
  fi
  if [ -z "$PARAKEET_BIN" ] && [ -x scripts/v6/provision_build_env.sh ]; then
    bash scripts/v6/provision_build_env.sh >/dev/null
    PARAKEET_BIN="$(choose_parakeet_bin || true)"
  fi
  if [ -z "$PARAKEET_BIN" ] && ensure_scoped_parakeet_venv; then
    PARAKEET_BIN="$(choose_parakeet_bin || true)"
  fi
  if [ -z "$PARAKEET_BIN" ]; then
    echo "No usable parakeet-mlx found. Its Python must import lzma and parakeet_mlx."
    exit 1
  fi
  INSTALLED_MODEL="/Applications/Anticipy.app/Contents/Resources/parakeet-tdt-0.6b-v3"
  if [ -z "${PARAKEET_MODEL:-}" ] && [ -d "$INSTALLED_MODEL" ]; then
    export PARAKEET_MODEL="$INSTALLED_MODEL"
  fi
  TRANSCRIPT_TMP="$EVAL_DIR/parakeet-output"
  rm -rf "$TRANSCRIPT_TMP"
  mkdir -p "$TRANSCRIPT_TMP"
  ASR_TIMEOUT="${MP3_ASR_TIMEOUT_SECONDS:-2400}"
  set +e
  run_bounded "$ASR_TIMEOUT" "$PARAKEET_BIN" "$MP3" \
    --output-dir "$TRANSCRIPT_TMP" \
    --output-format txt \
    --output-template transcript
  asr_status=$?
  set -e
  if [ "$asr_status" -ne 0 ]; then
    echo "parakeet-mlx failed or timed out with status $asr_status."
    write_json_failure "$EVAL_DIR/verdict.json" \
      "asr_failed_or_timed_out" \
      "parakeet-mlx exited $asr_status under MP3_ASR_TIMEOUT_SECONDS=$ASR_TIMEOUT"
    jq -n \
      --arg status "$asr_status" \
      --arg timeout "$ASR_TIMEOUT" \
      --arg mp3 "$MP3" \
      '{ok:false, status:($status|tonumber), timeout_seconds:($timeout|tonumber), mp3:$mp3}' \
      > "$EVAL_DIR/asr_failure.json"
    exit 1
  fi
  GENERATED_TRANSCRIPT="$(find "$TRANSCRIPT_TMP" -type f -name '*.txt' | sort | head -1)"
  if [ -z "$GENERATED_TRANSCRIPT" ] || [ ! -s "$GENERATED_TRANSCRIPT" ]; then
    echo "parakeet-mlx did not produce a non-empty transcript file in $TRANSCRIPT_TMP."
    exit 1
  fi
  cp "$GENERATED_TRANSCRIPT" "$TRANSCRIPT_CACHE"
fi
cp "$TRANSCRIPT_CACHE" "$EVAL_DIR/transcript.txt"
TRANSCRIPT_ABS="$(cd "$(dirname "$EVAL_DIR/transcript.txt")" && pwd -P)/$(basename "$EVAL_DIR/transcript.txt")"

# 2. Run the engine over the transcript. The engine emits one JSON line per action it would take.
echo "Running engine over transcript."
PAYLOAD="$(jq -n \
  --arg transcript_path "$TRANSCRIPT_ABS" \
  --argjson max_windows "${MP3_EVAL_MAX_WINDOWS:-240}" \
  --argjson max_chars_per_window "${MP3_EVAL_MAX_CHARS_PER_WINDOW:-900}" \
  --argjson max_processed_windows "${MP3_EVAL_MAX_PROCESSED_WINDOWS:-24}" \
  --argjson window_timeout_seconds "${MP3_EVAL_WINDOW_TIMEOUT_SECONDS:-20}" \
  '{
    transcript_path: $transcript_path,
    mode: "eval",
    dry_run: true,
    max_windows: $max_windows,
    max_chars_per_window: $max_chars_per_window,
    max_processed_windows: $max_processed_windows,
    window_timeout_seconds: $window_timeout_seconds
  }')"
if ! curl --max-time "${MP3_ENGINE_TIMEOUT_SECONDS:-900}" -sS -X POST http://127.0.0.1:8731/eval/run \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    > "$EVAL_DIR/engine_output.json"; then
  echo "Engine eval endpoint failed at http://127.0.0.1:8731/eval/run."
  exit 1
fi

if [ ! -s "$EVAL_DIR/engine_output.json" ]; then
  echo "Engine produced no output. Either it's not running or the eval endpoint isn't wired."
  exit 1
fi

# 3. Dispatch the evaluator sub-session.
PROMPT="You are running as the MP3 Evaluator per roles/mp3_evaluator.md.

Read these files (and ONLY these files):
- roles/mp3_evaluator.md (your rubric)
- $EVAL_DIR/transcript.txt (the held-out audio transcript)
- $EVAL_DIR/engine_output.json (the engine's actions)

Do NOT read:
- The engine source code
- Any planner, worker, or judge logs
- The contracts
- Any documentation

Write your verdict to $EVAL_DIR/verdict.json per the schema in your rubric.

Exit when verdict.json is written."

EVALUATOR_TIMEOUT="${MP3_EVALUATOR_TIMEOUT_SECONDS:-900}"
set +e
run_bounded "$EVALUATOR_TIMEOUT" \
  codex exec --sandbox danger-full-access --dangerously-bypass-approvals-and-sandbox "$PROMPT" \
  2>&1 | tee "$EVAL_DIR/evaluator.log"
evaluator_status=${PIPESTATUS[0]}
set -e

if [ "$evaluator_status" -ne 0 ]; then
  echo "Evaluator failed or timed out with status $evaluator_status."
  if [ ! -f "$EVAL_DIR/verdict.json" ]; then
    write_json_failure "$EVAL_DIR/verdict.json" \
      "evaluator_failed_or_timed_out" \
      "codex exec exited $evaluator_status under MP3_EVALUATOR_TIMEOUT_SECONDS=$EVALUATOR_TIMEOUT"
  fi
fi

if [ ! -f "$EVAL_DIR/verdict.json" ]; then
  echo "Evaluator did not produce verdict."
  write_json_failure "$EVAL_DIR/verdict.json" \
    "evaluator_no_verdict" \
    "codex exec completed without writing verdict.json"
  exit 1
fi

PASS=$(jq -r '.pass' "$EVAL_DIR/verdict.json")
GRADE=$(jq -r '.overall_grade' "$EVAL_DIR/verdict.json")
echo "MP3 eval verdict: pass=$PASS grade=$GRADE"
ln -sfn "$RUN_ID" state/mp3_eval/latest

if [ "$PASS" = "true" ]; then
  exit 0
else
  exit 1
fi
