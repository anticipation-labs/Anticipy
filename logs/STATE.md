# STATE

Current milestone: M0, ugly floor. Latest judged lap `20260606T025532Z` was `FAKE`; the unproven builder commit `2807f32aae57aee85093372916714eee79bc084d` was reverted by `1df9494`. Current builder lap `20260606T060511Z` is complete locally and awaiting judge verdict. M0 remains open until a fresh held-out real day produces a real verified artifact in a separate judge session.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Amended judge proof exists at `logs/verdicts/20260606T005447Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- Control-plane audio plumbing proof: capped builder-visible MP3 smoke `20260606T013101Z` transcribed 90 seconds of speech-gated local audio, reached the live engine, posted 15 transcript lines, and produced 15 ignores with zero actions. This is not judge proof.
- Judge proof for `20260606T013339Z` exists at `logs/verdicts/20260606T013339Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- Judge proof for `20260606T020452Z` exists at `logs/verdicts/20260606T020452Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, held-out MP3 `realdays/holdout/2026-05-21_08_11_04 2.mp3` ran end to end, Calendar/Gmail screenshots plus connector read-back attempts were saved, Gemini cross-check agreed with `FAKE` at confidence 1.0, and no current-lap real-world artifact was verified.
- Judge proof for `20260606T025532Z` exists at `logs/verdicts/20260606T025532Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean for forbidden paths and secrets, held-out MP3 `realdays/holdout/2026-05-21_12_19_20.mp3` ran end to end, Calendar/Gmail screenshots plus connector read-back attempts were saved, Gemini cross-check agreed with `FAKE` at confidence 1.0, and no current-lap real-world artifact was verified.
- Builder lap `20260606T060511Z` added an orchestrator-level external-action completion guard and support-only plan rejection. Focused orchestrator checks, a direct guard smoke, and `bash scripts/run_suite.sh` passed. Required builder-visible raw MP3 realday ran to completion with 3,228 transcript lines and decisions `act=28`, `ask=385`, `ignore=2815`; proof artifacts are `logs/last_realday.json` and `logs/trace/20260606T060511Z.jsonl`. This is not judge proof.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs, builder-side acts, DuckDuckGo searches, read-context proof, write-memory proof, stale eval artifacts, and support-only internal proof are not judge-verified M0 proof.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Judge laps `20260606T020452Z` and `20260606T025532Z` found Gmail read-only connector read-back returns `auth_status: pending`; UI screenshots were used for those verdicts, but a future Gmail artifact still needs connector read-back or a recorded scope gate.
- Lap `20260606T060511Z` judge verdict is PENDING.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/4 attempts verified, 0 percent. Current lap `20260606T060511Z` is not counted until judged.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Drift siren: DRIFT is active. Builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s started in `realdays/holdout/`; three are now burned by verdicts that actually attempted held-out days: `2026-05-20_17_34_13 2.mp3`, `2026-05-21_08_11_04 2.mp3`, and `2026-05-21_12_19_20.mp3`. Inventory-only filename lists do not burn days.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.
- Lap `20260606T060511Z` ran only builder-visible raw audio. It did not read holdout.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Do not treat a verdict inventory list as proof that every listed holdout day was read or burned.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, or screenshot-only browser proof as completed real-world actions for tasks that require sending, booking, creating, buying, posting, submitting, calling, or changing an external artifact.
- Do not let the planner type a whole task into the browser search bar as a substitute for decomposition. Explicit information lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not allow stale eval-literal goals such as old M0 proof Calendar/Gmail tasks, previous-lap ids, or old sent-mail subjects to contaminate held-out plans.

Next:
- Run the separate judge for lap `20260606T060511Z` on the remaining fresh held-out realday with planted-fake self-check, computer-use self-test, diff scan, real app proof, and different-family cross-check.
- If judge still finds false completion, inspect live planner output and `goal_done` proof types around the failing goals before adding another hand-level patch.
- Do not shrink M0 and do not count builder-visible raw audio as proof.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Oversight runs every lap regardless of cost. Work stays on `autopilot/build` until judge, different-family cross-check, diff scan, and tripwires all pass.
