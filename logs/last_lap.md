# Last Lap

Lap: 20260606T025532Z
Date: 2026-06-06T06:01:59Z
Milestone: M0 - ugly floor
ALL_MILESTONES_DONE: false

What changed:
- The builder added a generic browser-hand guard so read/search screenshot proof could not complete external action tasks such as sending, booking, buying, posting, submitting, or calling.
- The builder ran `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_hand.py`, `bash scripts/run_suite.sh`, and the required builder-visible MP3 realday.
- The separate judge then ran a fresh held-out MP3 end to end and ruled `FAKE`.
- The unproven builder commit `2807f32aae57aee85093372916714eee79bc084d` was reverted by gate in `1df9494`.

Judge checks:
- Planted-fake self-check passed at `logs/verdicts/20260606T025532Z_selfcheck.md`.
- Computer-use self-test passed with Chrome on `https://example.com`; screenshot is in `logs/verdicts/20260606T025532Z/computer_use_selftest_example_domain.png`.
- Tamper scan was clean for forbidden paths, secrets, and owner/student/eval literals in product code. The test diff contained prior-failure-style phrases and is recorded as a caution.
- Held-out run used `realdays/holdout/2026-05-21_12_19_20.mp3`, which is now burned.
- Held-out run completed with decisions `act=13`, `ask=176`, `ignore=1417` in about 498.961 seconds.
- OpenRouter cross-check used `google/gemini-3.5-flash` and agreed with `FAKE` at confidence 1.0.

Why it failed:
- No fresh current-lap Calendar or Gmail artifact was verified.
- Several `done` goals were only `write_memory`, `read_context`, or DuckDuckGo proof, not a real external artifact.
- A calendar-labeled meeting goal was marked `done` with only `read_context`.
- Stale eval-literal Calendar and Gmail artifacts from older laps contaminated current planning.
- Calendar and Gmail screenshots plus connector read-back attempts are saved under `logs/verdicts/20260606T025532Z/`.

Proof and status:
- Verdict: `logs/verdicts/20260606T025532Z.md`.
- Preserved held-out run artifacts: `logs/verdicts/20260606T025532Z/heldout_last_realday.json`, `logs/verdicts/20260606T025532Z/heldout_trace.jsonl`, and `logs/verdicts/20260606T025532Z/act_goal_summary.json`.
- M0 remains open. Generalization remains UNPROVEN. Reality judge verified pass rate is 0/4 under amended rules.
- DRIFT is active: builder tests remain 29/29 while reality judge pass rate remains 0 percent. Do not advance.

Next:
- Pivot at the planner and routing boundary. Do not add another browser regex patch.
- Stop whole task text from being typed into search as a substitute for planning. Browser search may only be proof for explicit information lookup tasks; action tasks must decompose into a real API hand, real browser agent hand, or ask/needs-human.
- Purge stale proof contamination from current-lap planning and make old eval titles or previous-lap proof ids abstain or ask, not act.
