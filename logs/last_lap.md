# Last Lap

Lap: 20260606T060511Z
Date: 2026-06-06T06:56:20Z
Milestone: M0 - ugly floor
ALL_MILESTONES_DONE: false

What changed:
- The builder added an orchestrator-level external-action completion guard and support-only plan rejection.
- Focused orchestrator checks, a direct guard smoke, and `bash scripts/run_suite.sh` passed.
- The required builder-visible raw MP3 realday ran to completion with 3,228 kept segments and decisions `act=28`, `ask=385`, `ignore=2815`.
- The separate judge ran a held-out realday and ruled `FAKE`.
- The unproven code slice from commit `590f1c060112134bcca12b9939c962cdbc027dcb` was reverted by the gate.

Judge checks:
- Planted-fake self-check passed at `logs/verdicts/20260606T060511Z_selfcheck.md`.
- Computer-use self-test passed with Chrome on `https://example.com`; screenshot is in `logs/verdicts/20260606T060511Z/computer_use_selftest_example_domain.png`.
- Tamper scan passed for the target builder commit and later control-plane commits.
- Held-out run completed with decisions `act=0`, `ask=49`, `ignore=394` in 129.922 seconds.
- Calendar and Gmail checks found no current-lap artifact; screenshots are in `logs/verdicts/20260606T060511Z/`.
- OpenRouter cross-check used a different model family and agreed with `FAKE` at confidence 1.0.

Why it failed:
- M0 requires a real task from a fresh unseen day to complete in a real app.
- The held-out run produced no current-lap real-world artifact.
- Calendar connector read-back and screenshots found no matching current-lap event.
- Gmail read-only connector read-back still returned `auth_status: pending`; Gmail Sent screenshot found no matching current-lap email.
- The guard reduced false completions but did not make the system act successfully on a real day.

Proof and status:
- Verdict: `logs/verdicts/20260606T060511Z.md`.
- Durable screenshot proofs: `logs/verdicts/20260606T060511Z/computer_use_selftest_example_domain.png`, `logs/verdicts/20260606T060511Z/calendar_search_current_lap_no_results.png`, and `logs/verdicts/20260606T060511Z/gmail_sent_search_current_lap_no_results.png`.
- Raw held-out traces and raw read-back JSON are local-only and ignored.
- Failed judge runs do not burn held-out days under Amendment 2.
- M0 remains open. Generalization remains UNPROVEN. Reality judge verified pass rate is 0/5 under amended rules.
- DRIFT is active: builder tests remain 29/29 while reality judge pass rate remains 0 percent. Do not advance.

Next:
- Move a perimeter milestone slice next, preferably M2 real app input, while still running the whole-house realday. Do not spend a fourth consecutive lap only on inference/brain.
- Keep the lesson from the human FYI: whole-task text in a search bar is not thinking. Search is allowed only for explicit information lookup; action tasks must decompose into API hands, the real browser agent hand, or ask/needs-human.
- Do not add another narrow browser regex patch. Fix routing or product perimeter, then judge it.
