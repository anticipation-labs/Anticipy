#!/usr/bin/env bash
# dispatch_planner.sh — spawn a fresh Codex sub-session as the Planner.
#
# Inputs (env):
#   CYCLE — cycle number
#   CYCLE_DIR — path like state/cycle-N
#
# Output: state/cycle-N/tasks.json (or state/COMPLETE.md if planner concludes done)
#
# Uses `codex exec` (non-interactive Codex CLI mode). Codex reads the planner role,
# the contracts, and produces JSON or COMPLETE.md.

set -euo pipefail

: "${CYCLE:?must be set}"
: "${CYCLE_DIR:?must be set}"

PROMPT="You are running as the Planner per roles/planner.md. Read these files in this order, then produce your output:

1. roles/planner.md  (your role)
2. contracts/DONE.md  (exit criteria)
3. contracts/URLS.md  (URL contract)
4. contracts/FROZEN.md  (invariants)
5. state/STATUS.md  (overall progress, if exists)
6. state/cycle-$((CYCLE - 1))/judge_verdict.json  (last cycle's verdicts, if exists)

Then:
- Run \`bash scripts/regression.sh\` and capture its output. Note which exit criteria are red.
- Walk git status, git log -10, and key directories to understand current state.
- Keep reads bounded. Do not dump full app source files. For source inspection use \`rg -n\`, \`git ls-files\`, and at most 80-line \`sed -n\` windows around relevant matches. Do not read files larger than 25 KB end to end.
- If E0 is red, produce exactly one deploy-parity worker task immediately. If E1 is red, produce exactly one E1 worker task immediately after confirming the route files. Do not inspect E2 or later until E0 and E1 are green.
- Produce \`$CYCLE_DIR/tasks.json\` per the schema in roles/planner.md.

If ALL of these conditions hold:
- scripts/regression.sh exits 0
- The last 3 MP3 evals at state/mp3_eval/verdict-*.json all show pass=true
- The last 3 stranger runs (if any) at state/stranger-runs/*/verdict.json show pass=true
- The last 10 regression runs at state/regression-*.log show success

Then instead of writing tasks.json, write state/COMPLETE.md with a one-paragraph summary of what was completed.

You may not write code. You may only edit \`$CYCLE_DIR/tasks.json\`, \`state/COMPLETE.md\`, or \`state/decisions/queue.md\`. Any other file edit is a violation.

Exit when tasks.json (or COMPLETE.md) is written."

# Use Codex CLI non-interactive exec. Current Codex CLI does not support
# the older --auto/--no-input flags and defaults child exec sessions to a
# read-only sandbox, so explicitly grant the child session repo write access.
codex exec --sandbox danger-full-access --dangerously-bypass-approvals-and-sandbox "$PROMPT" 2>&1 | tee "$CYCLE_DIR/planner.log"
