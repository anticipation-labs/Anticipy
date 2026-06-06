# Last Lap

Lap: 20260606T070041Z
Date: 2026-06-06T08:20:19Z
Milestone: M0 - ugly floor, with attempted M2 real app input perimeter slice
ALL_MILESTONES_DONE: false

What changed:
- The builder replaced the inert Mac app side-door text with a real typed task input in `macapp/Sources/AnticipyApp/MainView.swift`.
- The builder added `TaskInputModel`, posting `{"source":"app","text":...}` to `http://127.0.0.1:8787/event`, plus submit state, Return-key submit, and feed/pending refresh.
- The builder rebuilt the tracked local app bundle at `macapp/dist/Anticipy.app`.
- The separate judge ruled `FAKE`, so the unproven builder code slice from commit `04f28eacac4529ab39898a0158b3b632237f96f4` was reverted by the gate.

Builder verification before judge:
- `bash macapp/scripts/build_app.sh` passed.
- A harmless app-source API smoke posted to `/event`, returned `decision=ignore`, and appeared in glassbox.
- Computer Use launched the built app and reached the Main surface, but did not reliably expose or focus the edited field because pending asks filled the surface.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.
- Required builder-visible raw MP3 realday ran with `AUTOPILOT_LAP=20260606T070041Z bash scripts/realday.sh`, used builder-visible raw audio id `2026-05-20_07_34_11`, kept 3,228 segments, and returned `act=28`, `ask=385`, `ignore=2815` in 1,802.66 seconds. This was not judge proof.

Judge checks:
- Planted-fake self-check passed at `logs/verdicts/20260606T070041Z_selfcheck.md`.
- Computer-use self-test passed with Chrome on `https://example.com`; screenshot is in `logs/verdicts/20260606T070041Z/computer_use_selftest_example_domain.png`.
- Tamper scan passed for target builder commit `04f28eacac4529ab39898a0158b3b632237f96f4`.
- Held-out run completed with decisions `act=31`, `ask=271`, `ignore=1690` in 1,617.645 seconds.
- Calendar and Gmail read-back/screenshots found no current-lap artifact; screenshots are in `logs/verdicts/20260606T070041Z/`.
- OpenRouter cross-check used a different model family and agreed with `FAKE` at confidence 1.0.

Why it failed:
- M0 requires a real task from a fresh unseen day to complete in a real app.
- The held-out run produced no current-lap real-world artifact in Calendar, Gmail, browser, or any other external app.
- The judge found 31 apparent completions, all backed by internal `read_context` jobs.
- Pending asks and internal context reads are not real task completion.
- The M2 app input slice was not directly proven through app UI typing and did not lead to judged real action.

Proof and status:
- Verdict: `logs/verdicts/20260606T070041Z.md`.
- Durable screenshot proofs: `logs/verdicts/20260606T070041Z/computer_use_selftest_example_domain.png`, `logs/verdicts/20260606T070041Z/calendar_search_current_lap_no_results.png`, and `logs/verdicts/20260606T070041Z/gmail_sent_search_current_lap_no_results.png`.
- Raw held-out traces, raw read-back JSON, raw cross-check JSON, and raw pending/glassbox snapshots are local-only and ignored.
- Failed judge runs do not burn held-out days under Amendment 2.
- M0 remains open. Generalization remains UNPROVEN. Reality judge verified pass rate is 0/6 under amended rules.
- DRIFT is active: builder tests remain 29/29 while reality judge pass rate remains 0 percent. Do not advance.

Next:
- Move a perimeter milestone slice next, preferably M2 real app input again, but make the field directly visible and inspectable even when pending asks fill the surface.
- Keep the lesson from the human FYI and this verdict: whole-task search and internal `read_context` done goals are not thinking or acting.
- Real action tasks must decompose into API hands, the real browser agent hand, or ask/needs-human.
