#!/usr/bin/env bash
# spawn_codex_worker.sh — run a Codex worker that ALWAYS receives the mission context pack first.
# Codex is a worker, not the foreman: it cannot redefine done or self-grade; its patch must be
# attacked by an independent skeptic before the foreman integrates it.
#
# Usage:
#   bash scripts/agent_os/spawn_codex_worker.sh "your task description"
#   echo "task" | bash scripts/agent_os/spawn_codex_worker.sh
# Env:
#   CODEX_SANDBOX   default "workspace-write" (use "read-only" for skeptic/review workers)
#   CODEX_EFFORT    default "high" (use "xhigh" for hard architecture/safety/browser work)
#   CODEX_EXTRA     extra args passed to `codex exec`
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TASK="${1:-$(cat)}"
[ -n "${TASK// }" ] || { echo "no task given" >&2; exit 2; }

SANDBOX="${CODEX_SANDBOX:-workspace-write}"
EFFORT="${CODEX_EFFORT:-high}"

PROMPT="$(bash "$REPO/scripts/agent_os/context_pack.sh")
================ YOUR TASK ================
$TASK

REQUIRED OUTPUT (no self-grading):
- changed files + commands you ran
- the human-openable RECEIPT proving it (artifact read-back, screenshot+DOM, or test that can fail)
- how an independent skeptic could break it
- whether you touched any forbidden area (you must not)
Work in this repo only. Do NOT commit while factory/.lock exists. Do NOT edit .env*, scoring
thresholds, hidden holdout content, or receipt/failure ledger history. Stop before any irreversible
action (send/buy/pay/submit/delete/file) and before any live text/call."

command -v codex >/dev/null 2>&1 || { echo "codex CLI not found on PATH" >&2; exit 3; }

echo "[spawn_codex_worker] sandbox=$SANDBOX effort=$EFFORT cd=$REPO" >&2
exec codex exec --cd "$REPO" --sandbox "$SANDBOX" -c model_reasoning_effort="$EFFORT" \
  --json ${CODEX_EXTRA:-} "$PROMPT"
