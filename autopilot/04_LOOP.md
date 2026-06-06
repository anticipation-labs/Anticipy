# 04 LOOP — how one lap runs, and the runner

## Why it is built this way
Long autonomous runs fail when one session's context grows huge and the model drifts. The fix, proven across 2026 practice, is the opposite: every lap is a brand-new session with a fresh context, and all memory lives in files and git, not in the conversation. So each lap reads the state from disk, does one small vertical slice, gets judged against reality, writes what happened, and ends. The next lap starts clean.

## The runner
`autopilot/loop.sh` runs laps until the milestones in `07_MILESTONES.md` are all done, or a human gate is hit. Pseudocode:

```
while milestones_remain and not human_gate_open:
    build_lap        # fresh builder session, one slice + whole-house real-day run
    judge_lap        # fresh, separate judge session, opens real apps via computer use
    gate             # keep or revert based on the judge's verdict and the scorecard
    rotate logs, pick the next slice
done
notify the human: milestones done, or blocked at a gate
```

Each `build_lap` and `judge_lap` is a separate fresh Codex session (confirm the exact non-interactive launch command from the official docs during setup). The builder and the judge are never the same session. That separation is Law 1.

## One BUILD lap, concretely
The builder session is launched with a prompt like this:

```
You are one build lap for Anticipy. Fresh context. Do exactly this:
1. Read autopilot/02_LAWS.md, CODEX_BRIEF.md, logs/last_lap.md, and the top OPEN item in autopilot/07_MILESTONES.md.
2. Do the single next vertical slice toward that milestone. Smallest real step that moves the whole system forward. Use computer use as needed.
3. Run the whole system on a real day: bash scripts/realday.sh (it picks a builder-visible real day, never a holdout one).
4. Write logs/trace/<lap>.jsonl (every step), append logs/journal.md, and write logs/last_lap.md (what you did, the harness result, what is next).
5. Do NOT touch anything under tests/realday/ , realdays/holdout/ , or judge/ . Those belong to the judge. Editing them is a Law 4 violation.
6. Commit your work on autopilot/build with a one-line message. Stop. Do not declare success; the judge decides.
```

Rules inside a build lap:
- One slice per lap. Resist doing five things; small slices keep the judge meaningful and the context clean.
- Research official docs before any config edit or unfamiliar command (Law 7).
- Two honest tries on any fix, then rip out, log the failure, pivot (Law 6).
- Never route work to the human; only real gates go to `PENDING_FOR_OMAR.md` (Law 8).

## One JUDGE lap
Run per `05_JUDGE.md`. In short: a fresh separate session, computer use on, takes a real day the builder has never seen, runs the system, then opens the real apps and confirms whether the real artifact exists. It first runs a planted-fake self-check, and it scans the builder's last commit for edits to tests or judge files. It writes a verdict with screenshot proof to `logs/verdicts/`, which the builder may never write to.

## The GATE
After the judge rules:
- Verdict REAL, and the scorecard's verified-on-fresh-days count went up or held, and no regression fired: keep the commit, mark the slice done, advance the milestone if its done-criterion is met.
- Verdict FAKE or REGRESSED, or a test/judge file was tampered with, or the planted-fake check failed: revert the slice (`git revert` or reset the lap's commit), save the failing real day into `tests/realday/regressions/` as a permanent case, and do not advance. Next lap tries a different approach.
- Human gate hit at any point: append the specific need to `PENDING_FOR_OMAR.md`, keep working on anything not blocked, and only pause fully if everything is blocked.

## What we are climbing
Not a green 100 percent. There is no 100 percent; real days are endless. The one number to drive up and never let slide is verified real tasks on fresh, never-seen days (the scorecard in `06_LOGGING.md`). The first numbers will be ugly. Log them ugly. The loop's only job is to bend that curve up without faking.
