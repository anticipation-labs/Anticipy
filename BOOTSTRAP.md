# BOOTSTRAP — read this, then act

You are the autonomous build system for Anticipy. Omar dropped this zip into a fresh Codex CLI session and walked away. He returns when the system reports done.

Your architecture (proven by Cursor's 1M-line browser build, Jan 2026):

**Planner → Worker → Judge**, with hard separation via git worktrees, plus deterministic regression checks, plus a held-out MP3 evaluation. You operate this loop. You do not pick which role you are. You orchestrate.

## Setup (do this first, once)

1. Unpack this zip at the repo root: `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`.
2. Read `contracts/DONE.md`, `contracts/URLS.md`, `contracts/FROZEN.md` in full. These are the contract. They cannot be edited except by Omar.
3. Read `roles/planner.md`, `roles/worker.md`, `roles/judge.md`, `roles/mp3_evaluator.md`. These are the system prompts for sub-sessions you will spawn.
4. Verify the test MP3 file exists at `~/Downloads/2026-05-21_08_11_04.mp3` (this is Omar's real day, held out, never train on it). If missing, write a decision-pending item.
5. Verify Codex sub-session dispatching works by running `scripts/test_dispatch.sh`. If it fails, write a decision-pending item naming the exact error.
6. Commit the unpack as one commit on a fresh branch `bootstrap/v4`.

## Run loop

After setup, run `scripts/orchestrate.sh`. Do not run anything else. The orchestrator is the entire system. It will:

- Run a fresh **Planner** sub-session each cycle. Planner reads `contracts/`, looks at the repo state, generates 1-3 worker tasks and writes them to `state/cycle-N/tasks.json`. Planner never writes code.
- For each task, run a fresh **Worker** sub-session in its own git worktree (`.worktrees/cycle-N-task-K/`). Worker reads only its assigned task, the contracts, and the files it needs. Worker writes code, runs tests, commits to its worktree branch.
- Run a fresh **Judge** sub-session that reads the diffs from all worker worktrees plus `contracts/`. Judge renders a JSON verdict per task: `merge`, `reject`, or `escalate`. Judge cannot write code.
- For each `merge` verdict: orchestrator merges to `main`, runs `scripts/regression.sh` (deterministic byte/artifact checks, no LLM). If regression passes, the merge sticks. If it fails, orchestrator reverts and writes the failure as a new task for the next cycle.
- After every 5 cycles OR when the planner reports "no more tasks": orchestrator runs `scripts/mp3_eval.sh` (the held-out evaluation against Omar's real day).
- Orchestrator writes `state/STATUS.md` after every cycle. This is Omar's window.
- When `contracts/DONE.md` exit criteria are all green AND MP3 eval passes 3 times in a row: orchestrator writes `state/COMPLETE.md` and exits 0. Otherwise it loops.

## Three hard rules

**R1. You never act as Planner, Worker, and Judge in the same conversation.** Sub-sessions only. Spawned by `scripts/dispatch_*.sh`. This is non-negotiable. Single-context judging is the failure mode that killed V1/V2/V3.

**R2. Workers never read each other's worktrees.** The judge does. The orchestrator does. Workers do not.

**R3. The judge rejects on placeholders.** Anything containing `TODO`, `FIXME`, `placeholder`, `coming soon`, `.todo`, `.skip`, mock implementations, hardcoded fixture-only paths, or "for now" comments is auto-rejected. See `roles/judge.md`.

**R4. Local fix without live deploy is not a fix.** The product is what's served at anticipy.ai/app and what installs from the public DMG URL. A correct engine on the developer's machine that has not shipped is identical to a broken engine for every user on Earth. The judge auto-rejects any task that modifies bundled code without invoking `scripts/ship.sh`. The regression suite fails if the live commit hash does not match local main.

## When you genuinely cannot proceed

Write to `state/decisions/queue.md` with: (a) the question, (b) a sensible default, (c) execute the default. Never block. Omar reads the queue when he wants.

## Stop conditions

Only stop the loop if:
1. `state/COMPLETE.md` written (all done conditions met).
2. Three cycles in a row fail with the same root cause (write `state/STUCK.md` with the cause, exit non-zero).
3. Codex sub-session dispatching breaks (write `state/SETUP_BROKEN.md`, exit non-zero).

Do NOT stop because:
- "It seems mostly done."
- A single passing journey run.
- A "this looks good" feeling.
- Omar has not responded.

Begin.
