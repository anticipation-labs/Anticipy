# Cron cycle procedure (v2: discovery first)

The cron fires every 3 minutes. Each fire calls this procedure. The procedure is mechanical. No improvisation. If a step says verify, the planner must actually run the verify command and read the output.

The v1 procedure was queue-execute-status. That was wrong. The v1 declared "done" by clearing 16 internal work units, not by proving the product works for a real user. The v2 below adds a Discovery step at the top, reframes done criteria in user terms, and counts stagnation.

## Step 0. Discovery (the new step that forces convergence on the North Star)

Before touching the queue, act as a real user for one minute. Pick one of:

- **Trivia user.** Curl `/api/listen/inject` with a trivia phrase ("wait, when did X happen") that has NOT been tested this session. Check `/api/trivia/recent` for the fire. Verify the answer is correct. Verify audio actually played (check `/usr/bin/say` was spawned).
- **Silent-execute user.** Curl `/api/listen/inject` with a real action phrase ("draft a thank-you email to Joe from PostHog"). Open the user's Chrome via CDP, navigate to mail.google.com/drafts, confirm a draft appeared with that recipient + body.
- **Cold-start user.** Wipe `~/.anticipy/v7/dossiers/<acct>/dossier.json`, hit `POST /api/coldstart/start`, poll status, verify ≥ 10 real people appear in the dossier within 60s.
- **Popover user.** Open the Tauri menubar popover via `open /Applications/Anticipy.app`. Screenshot it via computer-use. Check it renders correctly, no crashes, no stale data.
- **Notification user.** Trigger a `notify-after` event via `/api/notify/test`. Check the macOS notification banner actually appears (computer-use screenshot).

If discovery finds a bug: log a new work unit in ORCHESTRATOR.md with `status: queued`, owner unassigned. The cron will spawn an agent for it on the next eligible cycle.

If discovery finds no bug: log `discovery: no new bugs found this cycle` in the status line.

EITHER way, you have made progress this cycle.

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

## Step 3. Advance the scoreboard (mechanical, not vibe)

Compute the 6 user-facing gate states from the verify commands below. Update the scorecard section of ORCHESTRATOR.md. NO percentage estimates. ONLY GREEN or RED per gate.

The 6 user-facing gates (the new mechanical 100% marker):

| Gate | Mechanical verify | Pass criterion |
|---|---|---|
| **G1 install_under_5min** | `bash scripts/v7/stranger_flow.sh` exits 0 + result.json shows total_elapsed_sec < 300 | a fresh user can install + onboard in < 5min |
| **G2 trivia_fires** | `python scripts/v7/discovery_trivia.py` exits 0 (planted trivia phrase + audio plays + correct fact) | trivia-fire latency < 2s, answer correct, audio actually plays |
| **G3 silent_execute** | `python scripts/v7/z001_e2e_harness.py` exits 0 with verdict=PASS | spoken action becomes real Gmail draft via real Chrome |
| **G4 coldstart_fills_dossier** | `python scripts/v7/discovery_coldstart.py` exits 0 (wipe + inhale + ≥10 real people in 60s) | day-0 useful |
| **G5 packaged_binary_serves** | `ps -p $(lsof -t :8731) -o command=` matches `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` AND `curl /api/trivia/recent` returns 200 (not 404) | the DMG-shipped binary actually has the new features |
| **G6 demo_rehearsed** | `state/demo/dress_rehearsal_log.json` shows two consecutive PASS runs within the last 4 hours | demo isn't theoretical |

Stop the cron only when ALL 6 are GREEN.

## Step 4. Check the done criteria

If all 6 gates GREEN: write `state/orchestrator/DONE.json`. Set cron message to "DONE. Notify user." End cycle.

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

## Step 7. Write status line + count stagnation

Single-line status to the bottom of the status log in ORCHESTRATOR.md. Format:
`cycle <N> | <time> | discovery: <found_X_or_clean> | gates: <G1..G6 GR pattern> | next action: <what> | stagnation: <0|1|2|3>`

Increment stagnation if BOTH:
- No new commit landed since the last cycle that was not just a status log.
- No new bug found in discovery this cycle.

Reset stagnation to 0 on any commit or discovery hit.

## Step 8. Self-arm OR escalate

If 6 gates GREEN: declare DONE. Notify user. Cron remains active for monitoring but produces no new work.
If stagnation hits 3: write `state/orchestrator/STUCK.json`. Set cron message to "STUCK. Need owner attention." Continue running but only re-verifying, not spawning new work, until owner intervenes.
Otherwise: the cron will fire again in 3 min.

## What this planner agent (the cron-fired one) does NOT do

- Does NOT edit source code directly. Execution agents do that.
- Does NOT decide product direction. The owner does. Open questions go to a designated section of ORCHESTRATOR.md.
- Does NOT skip verify steps. Mechanical verify is the basis of trust.
- Does NOT claim done on its own authority. Only verify commands flip status.
- Does NOT use em-dashes. Owner rejects on sight.
- Does NOT report scorecard percentages. Only the 6 user-facing gates count.

## Trust contract with the owner

- The owner does not check in. The cron runs. The orchestrator advances. The owner is notified when DONE or STUCK.
- The orchestrator file is human-readable so the owner can audit at any time without asking the planner.
- Every `done` status is backed by a verify command the owner can run themselves.
- No "I assure you it works" messages. Only "verify command X exited 0 at time Y" messages.

## How a new planner picks up this procedure

If a different cron fire lands a different planner (because the runtime spun up a new instance), the new planner reads:
1. `planning/00-handoff/HANDOFF_FOR_NEXT_AGENT.md` (the architectural rules)
2. `planning/00-handoff/ORCHESTRATOR.md` (current state)
3. This file (`CYCLE_PROCEDURE.md`) (what to do)

And follows the procedure from step 0.
