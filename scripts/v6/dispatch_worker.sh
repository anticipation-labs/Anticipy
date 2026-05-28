#!/usr/bin/env bash
set -euo pipefail

: "${CYCLE:?}"
: "${CYCLE_DIR:?}"
: "${TASK_ID:?}"
: "${WORKTREE:?}"
: "${TASK_FILE:?}"

ORCHESTRATOR_REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$WORKTREE"
export REPO
REPO="$(pwd -P)"
export V6_DEFER_WORKTREE_SHIP=1
. "$ORCHESTRATOR_REPO/scripts/v6/dispatch_common.sh"

PROMPT="Read ANTICIPY_V7.md from disk. First restate PART 0 in your own words.
You are the Worker per roles/worker.md and the V7 target.
Task file: $TASK_FILE.
Worktree: $WORKTREE.

Read the task and only files in scope. Implement exactly that task, run the task success_test until it exits 0, then commit with message 'worker $TASK_ID: <summary>'. Do not start a source uvicorn or dev server on port 8731; product proof on that port must be /Applications/Anticipy.app/Contents/MacOS/anticipy-engine and must pass python3 scripts/v7/assert_installed_engine.py. If blocked, write $CYCLE_DIR/worker_${TASK_ID}_blocked.md with the exact blocker and exit non-zero."

run_codex_prompt "$PROMPT"
