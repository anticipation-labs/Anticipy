#!/usr/bin/env bash
# dispatch_worker.sh — spawn a fresh Codex sub-session as a Worker, scoped to one worktree.
#
# Inputs (env):
#   CYCLE, CYCLE_DIR, TASK_ID, WORKTREE, TASK_FILE
#
# The worker operates inside $WORKTREE only. It reads $TASK_FILE for its single task.

set -euo pipefail

: "${CYCLE:?}"
: "${CYCLE_DIR:?}"
: "${TASK_ID:?}"
: "${WORKTREE:?}"
: "${TASK_FILE:?}"

WORKTREE_ABS="$(cd "$WORKTREE" && pwd -P)"
CYCLE_DIR_ABS="$(cd "$CYCLE_DIR" && pwd -P)"
TASK_FILE_ABS="$(cd "$(dirname "$TASK_FILE")" && pwd -P)/$(basename "$TASK_FILE")"

PROMPT="You are running as a Worker per roles/worker.md. Your working directory is $WORKTREE_ABS. Your task is in $TASK_FILE_ABS.

Steps:
1. Read roles/worker.md (your role rules).
2. Read $TASK_FILE_ABS (your single task).
3. Read contracts/DONE.md, contracts/URLS.md, contracts/FROZEN.md.
4. Read ONLY the files inside the task's 'scope'. Do not read files outside scope unless absolutely required.
5. Implement the task. Stay strictly within 'scope'. Respect 'out_of_scope'.
6. Run the task's success_test (bash command in the JSON). If it exits 0, commit and exit. If not, iterate. Fix the actual problem.
7. Use a clear commit message: 'worker $TASK_ID: <one-line summary>'.

You MAY NOT:
- Read other worktrees at .worktrees/cycle-*-task-* (besides your own)
- Edit $TASK_FILE_ABS or any tasks.json
- Edit files outside 'scope'
- Add placeholders, TODOs, stubs, or mock implementations
- Modify the success_test
- 'Refactor while I'm here' anything

If you cannot complete the task: write $CYCLE_DIR_ABS/worker_${TASK_ID}_blocked.md with the specific blocker and exit non-zero.

Exit when success_test exits 0 and you have committed."

cd "$WORKTREE_ABS"
codex exec --sandbox danger-full-access --dangerously-bypass-approvals-and-sandbox "$PROMPT" 2>&1 | tee "$CYCLE_DIR_ABS/worker-$TASK_ID.log"
