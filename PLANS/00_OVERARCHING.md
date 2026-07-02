# PLANS — The Overarching Board

## 1. What this folder is

MISSION_LOCK holds the milestones — the big promises Anticipy has to keep.
PLANS decomposes each promise into small steps that a non-coder can supervise, one checkbox and one proof at a time.
A milestone may NOT be marked PASSED off work that bypassed its FIX plan's proof boxes — no proof, no pass.

## 2. The status board

| FIX | Title | Serves | Status | Last verified |
|--------|----------------------------------------------------------------|-----------------|-------------|---------------|
| FIX-00 | canon-docs + gate | docs foundation | DONE | 2026-07-02 |
| FIX-01 | one-pipeline (proactive consolidation Phases 1-2) | M1 durability | OPEN | 2026-07-02 |
| FIX-02 | orphans (anticipate wire-or-delete, digest wire) | — | OPEN | 2026-07-02 |
| FIX-03 | deep-scrape-wire | M5 | OPEN | 2026-07-02 |
| FIX-04 | autonomy-wire | — | OPEN | 2026-07-02 |
| FIX-05 | profile-wire | — | OPEN | 2026-07-02 |
| FIX-06 | pending-wire | — | OPEN | 2026-07-02 |
| FIX-07 | true-proactive (derive + world_research + derive_tick) | the marquee | OPEN | 2026-07-02 |
| FIX-08 | remembered-panel | — | OPEN | 2026-07-02 |
| FIX-09 | voice-checklist | M6 | OPEN | 2026-07-02 |
| FIX-10 | deep-read-hand | — | OPEN | 2026-07-02 |
| FIX-11 | scrape-expansion | M5 | OPEN | 2026-07-02 |
| FIX-12 | browser-agent-ui | M4 | OPEN | 2026-07-02 |
| FIX-13 | gmail-compose-hand (`/hands/compose-email` — the #1 long pole; currently BROKEN: imports a nonexistent `hands/cdp_client`) | M4 | OPEN | 2026-07-02 |
| FIX-14 | ledger-surfaces (`/scorecard`, `/goals/{id}`, `/gateway`, `/api/glassbox` — wire a UI ledger view or retire) | — | OPEN | 2026-07-02 |
| FIX-15 | ws-control-plane (`/ws/state|reload|browse|observe|act`, `/api/browser/run`, `browser_use_runner` — product never drives them) | M4 | OPEN | 2026-07-02 |
| FIX-16 | download-button-wire (`/api/download/anticipy-execute` serves but no UI points at it) | M8 | OPEN | 2026-07-02 |
| FIX-17 | owner-session-wire (`/api/owner/session` — the login UI never calls it) | — | OPEN | 2026-07-02 |
| FIX-18 | trigger-tick-scheduler (`/api/trigger/tick` has no scheduler caller in the app) | — | OPEN | 2026-07-02 |
| FIX-19 | wiring-strict (burn every TODO in `factory/wiring_allowlist.txt` to zero; flip the gate to `--strict`) | — | OPEN | 2026-07-02 |

Statuses: OPEN (not started) · IN-PROGRESS (someone is working it) · DONE (every step checked with proof) · BLOCKED (see the plan's `[!]` line).

## 3. The rules

**R1 — Proof or it didn't happen.**
A step is `[x]` only when its WIRING-PROOF box has pasted real output + date.
Why: this repo has been fooled before by "verified" claims with nothing behind them. The proof box
is the receipt. An empty box under a checked step is the single loudest red flag in this system.

**R2 — Every plan ends at the gates.**
Every plan's final step = `bash scripts/run_suite.sh` (fail-set ⊆ Step-0 baseline) + `engine/.venv/bin/python factory/bin/check_wiring.py` (failure count shrunk or held) + commit.
Why: a fix that quietly breaks something else is not a fix. The gates compare the end state to the
Step-0 baseline, so "it works on my step" can never hide new damage.

**R3 — Steps stay small.**
One step ≤ ~30 min + exactly ONE proof command; plan ≤ 10 steps or split into FIX-NNa/NNb.
Why: a step Omar can't watch land in one sitting is a step he can't supervise. One command per step
means there is never an argument about which output counts as the proof.

**R4 — Cold-start preconditions.**
Step 0 of every plan = copy-paste preconditions so Omar can start supervision cold.
Why: supervision must not depend on remembering yesterday's terminal state. Anyone should be able to
open the plan on a fresh morning, paste Step 0, and know within a minute whether the ground is solid.

**R5 — Rollback first.**
Rollback written BEFORE the step runs.
Why: if the undo is written after things break, it gets written in a panic — or not at all. Writing
it first also forces the author to understand what the step actually touches.

## 4. How Omar supervises without reading code

Open the plan file, then check the boxes top to bottom — the story should make plain-English sense.
Any `[x]` with an empty proof box → call it out. That is the whole game.
Run the plan's "Human check" yourself — it never needs a terminal.
Run `git log --oneline -10` and ask which commit is which step.
If the answers are mushy, the work is mushy; send it back.

## 5. Checkbox convention

- `[ ]` open — not started
- `[~]` in progress — being worked right now
- `[x]` done + proof — the WIRING-PROOF box below it holds real pasted output + a date
- `[!]` blocked — with a `BLOCKED-ON:` line saying exactly what it's waiting on

The agent updates the checkbox + proof box in the SAME edit.
The plan file commits WITH the code it proves — so `git log -p PLANS/` is a tamper-evident audit trail: any checkbox flipped without its code (or proof) in the same commit sticks out immediately.

## How to start a new plan

1. Copy `PLANS/_TEMPLATE.md` to `PLANS/FIX-NN_<short-name>.md`.
2. Fill in every section — especially "What BROKEN looks like" and the Rollback lines (R5).
3. Add the row to the status board above and set it IN-PROGRESS when work starts.
4. Work top to bottom. One step, one command, one proof, one commit.
5. When the final gates pass, flip the board row to DONE with today's date.

## What "not worse" means (the two gates, in plain English)

- **The suite gate:** `scripts/run_suite.sh` runs everything. Whatever was already failing at Step 0 is the "baseline fail-set." After your work, the failing tests must be a subset of that baseline — you may fix failures, you may never add one.
- **The wiring gate:** `factory/bin/check_wiring.py` counts features that exist but aren't connected to anything (orphans). After your work, that count must be lower than or equal to the Step-0 count. Wiring work only counts if this number moves the right way.

If either gate is worse than baseline, the step is not done, no matter what the code looks like.

## Glossary (plain English)

- **Milestone (M1, M4, M5, M6...):** a big promise in MISSION_LOCK. FIX plans exist to serve them.
- **The marquee:** the headline behavior — Anticipy acting proactively without being asked (FIX-07).
- **The suite:** the full test run (`scripts/run_suite.sh`). Green means the known behaviors still work.
- **Fail-set:** the exact list of tests failing at Step 0. New work may shrink it, never grow it.
- **Wiring:** whether a built feature is actually connected to the running product, end to end.
- **Orphan:** code that exists but nothing calls — a hand with no arm. `check_wiring.py` counts these.
- **Proof box:** the fenced block under each step where real command output gets pasted, with a date.
- **Baseline:** the Step-0 measurements. Every later claim of "done" is judged against them.
- **The gates:** the two baseline comparisons (suite + wiring) every plan must pass before commit.
- **Tamper-evident:** because the plan file commits with the code, `git log -p PLANS/` shows exactly
  when each box was checked and what code shipped alongside it — checkboxes can't be quietly backfilled.
