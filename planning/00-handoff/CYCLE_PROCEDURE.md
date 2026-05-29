# Cron cycle procedure

The cron fires every 3 minutes. Each fire calls this procedure. The procedure is mechanical. No improvisation. No "I'll skip this step." If a step says verify, the planner must actually run the verify command and read the output.

## Step 1. Read state

Read `planning/00-handoff/ORCHESTRATOR.md`. Identify:
- Which units are `done`.
- Which units are `in-flight` (an agent or process is currently working on it).
- Which units are `queued` (work could start if dependencies are met).
- Which units are `blocked` (waiting on a dependency or a human decision).

## Step 2. Verify any unit claiming `done` or `in-flight` near completion

For each unit whose agent has reported success in the last cycle, run its verify command. If it passes:
- Flip status to `done`.
- Run Z-001 (`python3 scripts/v7/z001_e2e_harness.py`). If FAIL: revert the unit's commits with `git reset --hard HEAD~N` and flip status back to `queued` with a note.
- If PASS: merge the unit's worktree branch to main (if applicable) and write to the status log.

If the agent claims success but verify fails:
- Flip status to `queued` with `blocked_reason: verify_failed`.
- Note the specific failure in the status log.

## Step 3. Advance the scoreboard

Compute the scorecard from the unit `done` statuses. Update the scorecard section of ORCHESTRATOR.md. Compute total %.

## Step 4. Check the done criteria

If all 7 done criteria pass: write `state/orchestrator/DONE.json`. Set cron message to "DONE. Notify user." End cycle.

## Step 5. Schedule new work

For each `queued` unit whose dependencies are all `done`:
- Spawn an execution agent in a fresh git worktree.
- Pass the agent: the planning doc(s) it depends on, the file paths it owns, the verify command for its unit.
- Set status to `in-flight`.
- Cap concurrent agents at 16 across all units. If at cap, leave the unit queued.

## Step 6. Health check active agents

For each `in-flight` unit older than 15 minutes:
- Check if its worktree branch has any commits in the last 15 min.
- If yes: leave alone.
- If no: assume the agent is wedged. Kill it. Spawn a fresh one.

## Step 7. Write status line

Single-line status to the bottom of the status log in ORCHESTRATOR.md. Format:
`cycle <N> | <time> | <done>/16 units done | scorecard <X>% | next action: <what>`

## Step 8. Self-arm

If done criteria not yet met: do nothing (the cron will fire again in 3 min).
If done criteria met: cron message is "DONE." User is notified.

## What this planner agent (the cron-fired one) does NOT do

- Does NOT edit source code directly. Execution agents do that.
- Does NOT decide product direction. The owner does. Open questions go to a designated section of ORCHESTRATOR.md.
- Does NOT skip verify steps. Mechanical verify is the basis of trust.
- Does NOT claim done on its own authority. Only verify commands flip status.
- Does NOT use em-dashes. Owner rejects on sight.

## Failure mode: 3 consecutive cycles with no progress

If 3 cycles fire and no unit advances (no scorecard delta, no status flip):
- Write a full diagnostic to `state/orchestrator/STUCK.json`.
- Set cron message to "STUCK. Need owner attention." Notify the user.
- Continue running but only re-verifying, not spawning new work, until owner intervenes.

## How a new planner picks up this procedure

If a different cron fire lands a different planner (because the runtime spun up a new instance), the new planner reads:
1. `planning/00-handoff/HANDOFF_FOR_NEXT_AGENT.md` (the architectural rules)
2. `planning/00-handoff/ORCHESTRATOR.md` (current state)
3. This file (`CYCLE_PROCEDURE.md`) (what to do)

And follows the procedure from step 1.

## Trust contract with the owner

- The owner does not check in. The cron runs. The orchestrator advances. The owner is notified when DONE or STUCK.
- The orchestrator file is human-readable so the owner can audit at any time without asking the planner.
- Every `done` status is backed by a verify command the owner can run themselves.
- No "I assure you it works" messages. Only "verify command X exited 0 at time Y" messages.
