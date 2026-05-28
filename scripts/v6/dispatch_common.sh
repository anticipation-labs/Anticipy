#!/usr/bin/env bash
# Shared Codex dispatch helpers for V6 role scripts.

set -euo pipefail

run_dispatch_with_timeout() {
  local timeout_seconds="$1"
  shift
  local helper
  helper="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)/scripts/v6/run_with_timeout.py"
  if [ -f "$helper" ]; then
    python3 "$helper" "$timeout_seconds" "$@"
  elif command -v perl >/dev/null 2>&1; then
    perl -e 'alarm shift; exec @ARGV' "$timeout_seconds" "$@"
  else
    "$@"
  fi
}

run_codex_prompt() {
  local prompt="$1"
  if ! command -v codex >/dev/null 2>&1; then
    echo "codex CLI not found" >&2
    return 127
  fi
  local args=()
  if [ -n "${CODEX_EXEC_MODEL:-}" ]; then
    args+=(--model "$CODEX_EXEC_MODEL")
  fi
  if [ -n "${CODEX_EXEC_ENABLE_FEATURES:-}" ]; then
    local feature
    for feature in ${CODEX_EXEC_ENABLE_FEATURES//,/ }; do
      case "$feature" in
        "" )
          ;;
        computer-use|browser|chrome )
          # These are Codex desktop plugins loaded from config.toml, not CLI
          # feature flags. Passing them to `codex exec --enable` fails on
          # current Codex CLI builds with "Unknown feature flag".
          ;;
        * )
          args+=(--enable "$feature")
          ;;
      esac
    done
  fi
  args+=(--sandbox danger-full-access)
  args+=(--dangerously-bypass-approvals-and-sandbox)
  run_dispatch_with_timeout "${CODEX_EXEC_TIMEOUT_SECONDS:-5400}" \
    codex exec "${args[@]}" "$prompt"
}
