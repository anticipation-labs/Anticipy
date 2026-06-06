# 06 LOGGING — the progress spine (mandatory, continuous)

Agents fail in ways that look like success: well-formed but wrong output, pointless tool calls, actions that are valid but semantically wrong. A pass/fail line cannot catch that. The fix is step-level logging you can replay, plus a loop where every failure becomes a permanent test and a gate blocks fake progress. This logging is also the anti-fake mechanism: when every step and its proof are recorded, a fake is visible.

No silent work. A lap that leaves no trace is void (Law 9).

## What to write, every lap

### 1. Step-level trace: `logs/trace/<lap>.jsonl`
One JSON line per step. A step is any model call, tool call, command, file edit, browser action, or judge check. Suggested fields:
```
{ "ts": "...", "lap": 12, "phase": "build|test|judge|gate",
  "actor": "builder|judge", "action": "edit|run|browse|verify|...",
  "target": "file or url or app", "input_summary": "...",
  "result": "ok|fail + short", "proof_ref": "path to screenshot/output if any",
  "tokens": 0, "cost_usd": 0.0 }
```
This is the replayable transcript. It must be complete enough that someone can reconstruct exactly what happened and why.

### 2. Scorecard: `logs/scorecard.csv`
One row per lap. This is the curve we actually watch.
```
lap, date, milestone, realday_id, judge_verdict,
real_tasks_attempted, real_tasks_verified, false_actions, regressions,
taste_confidence, cost_usd, wall_seconds, notes
```
- `real_tasks_verified` on fresh, never-seen days is THE number. It must go up over time and never slide back.
- `false_actions` (acted on a vent or a non-task) must stay zero. A single false action fails the lap.
- `taste_confidence` is LOW until enough human-marked days exist; while LOW, do not claim judgment progress.
- Every scorecard row must include or mention the drift numbers: own tests' pass rate and reality judge verified pass rate on fresh unseen days. If the schema cannot hold both cleanly, put them in `notes`.
- Until real diverse users exist, every scorecard row must label generalization as `UNPROVEN` in `notes`. Never claim the product works for everyone.

### 3. `logs/last_lap.md`
A short human-readable summary of the most recent lap: what was tried, the judge's verdict, what is next. Every fresh lap reads this first.

### 4. `logs/journal.md`
Append-only. One short paragraph per lap, plain language, so the human can skim the whole history top to bottom.

### 5. `logs/STATE.md`
Rewrite this at the end of every lap. It must include: current milestone, what is proven with judge verdict and proof link, what is pending a human gate, drift numbers, dead ends not to retry, and a one-line digest of the laws. Every fresh lap reads this before doing work.

## The feedback loop (failure becomes a permanent test)
When the judge rules FAIL or REGRESSED on a real day, save that day (or the exact failing slice) into `tests/realday/regressions/` as a permanent case. From then on, the loop must never regress on it. The test suite grows from real failures, not from cases the builder invented. The builder may not edit this folder (Law 4).

## The gate
A change is kept only if all of these hold:
- the reality judge ruled REAL,
- the different-family cross-check agreed,
- the judge self-checks passed,
- the diff scan was clean of secrets, hardcoded eval literals, and forbidden edits,
- `real_tasks_verified` went up or held,
- `false_actions` is zero,
- no regression case fired,
- the tamper scan found no edits to tests or judge files.
Otherwise the lap is reverted and the failure is saved as a regression test.

## Drift siren, checked every lap
Track two numbers every lap: the builder-owned tests' pass rate, and the reality judge's verified pass rate on fresh unseen days. If the builder-owned pass rate climbs while the reality judge rate stays flat or falls, STOP, write `DRIFT` in `logs/journal.md`, and do not advance. That gap is the signature of overfitting or gaming.

## Oversight is uncapped
The judge, different-family cross-check, planted-fake self-check, computer-use self-test, and diff scan run every lap in full, regardless of token cost, spend, or compute. Never skip or shorten oversight to save tokens or time. The watchers do not care about cost; they only care that the proof is real.

## How the human watches progress
The human should be able to see, at any time, without you:
- `logs/journal.md` (the running story),
- `logs/scorecard.csv` (the curve),
- `PENDING_FOR_OMAR.md` (anything waiting on them),
- the macapp glass-box feed (the live engine, already wired).
Keep these current. They are how the human trusts the run without babysitting it.
