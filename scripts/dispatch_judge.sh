#!/usr/bin/env bash
# dispatch_judge.sh — spawn a fresh Codex sub-session as the Judge.
#
# Inputs (env):
#   CYCLE, CYCLE_DIR, JUDGE_INPUT
#
# Output: $CYCLE_DIR/judge_verdict.json

set -euo pipefail

: "${CYCLE:?}"
: "${CYCLE_DIR:?}"
: "${JUDGE_INPUT:?}"

PROMPT="You are running as the Judge per roles/judge.md. You have a fresh context and no awareness of why these changes were made or what the workers were thinking.

Steps:
1. Read roles/judge.md (your role).
2. Read contracts/DONE.md, contracts/URLS.md, contracts/FROZEN.md.
3. Read $JUDGE_INPUT (the manifest with tasks, diffs, success_test results).
4. For each task in the manifest, apply the mechanical rules in roles/judge.md. Auto-reject on tokens, scope, frozen-path, brand. Merge if all rules pass and success_test exited 0. Escalate if success_test passed but the diff doesn't actually fulfill the contract.
5. Write $CYCLE_DIR/judge_verdict.json per the schema in roles/judge.md.

You MAY NOT:
- Read state/cycle-$CYCLE/tasks.json rationale fields (only the task definitions are yours)
- Read state/cycle-$CYCLE/planner.log
- Read state/cycle-$CYCLE/worker-*.log
- Run the success_tests yourself (the orchestrator already did; you read results from JUDGE_INPUT)
- Edit any file other than $CYCLE_DIR/judge_verdict.json
- Be generous. The trillion-dollar bar from DONE.md applies.

Exit when judge_verdict.json is written."

codex exec --sandbox danger-full-access --dangerously-bypass-approvals-and-sandbox "$PROMPT" 2>&1 | tee "$CYCLE_DIR/judge.log"
