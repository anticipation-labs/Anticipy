# STATE

Current milestone: M0, ugly floor. Latest judged lap `20260606T060511Z` was `FAKE`: the separate judge ran a held-out realday, found `act=0`, `ask=49`, `ignore=394`, and verified no current-lap Calendar or Gmail artifact. The latest builder lap `20260606T070041Z` moved a perimeter slice toward M2 real app input while M0 remains open. Judge verdict for `20260606T070041Z` is `PENDING`.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260606T060511Z.md`. The latest judged reality result is still `FAKE`, with no current-lap real artifact verified.
- Amendment 2 is active: raw traces, `logs/last_realday.json`, transcript files, `.anticipy-data/`, and raw verdict JSON/JSONL are local-only and ignored. Durable builder-readable files contain verdicts, counts, proof links, and lessons only, not raw held-out transcript text.
- Builder lap `20260606T070041Z` made the Mac app typed task side-door real: it posts app-source task text to `/event`, reports submit state, and refreshes feed and pending state after successful handoff.
- Builder verification for `20260606T070041Z`: `bash macapp/scripts/build_app.sh` passed; a harmless app-source API smoke returned `decision=ignore` and appeared in glassbox; Computer Use launched the built app and reached the Main surface, but did not reliably expose or focus the edited field because pending asks filled the surface; `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.
- Required builder-visible realday for `20260606T070041Z` ran with `AUTOPILOT_LAP=20260606T070041Z bash scripts/realday.sh`, used builder-visible raw audio id `2026-05-20_07_34_11`, kept 3,228 segments, returned `act=28`, `ask=385`, `ignore=2815`, and took 1,802.66 seconds. This is not judge proof.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs, builder-side acts, DuckDuckGo searches, read-context proof, write-memory proof, channel-stub proof, stale eval artifacts, support-only internal proof, and the new typed input path are not judge-verified M0 proof.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Judge laps `20260606T020452Z`, `20260606T025532Z`, and `20260606T060511Z` found Gmail read-only connector read-back returns `auth_status: pending`; UI screenshots were used for those verdicts, but a future Gmail artifact still needs connector read-back or a recorded scope gate.
- Judge verdict for builder lap `20260606T070041Z` is pending.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/5 attempts verified, 0 percent.
- Latest builder-visible realday: `act=28`, `ask=385`, `ignore=2815`; judge has not ruled.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet. Generalization remains UNPROVEN.
- Drift siren: DRIFT is active. Builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. Under Amendment 2, a held-out day is burned only when it contributes to a milestone PASS. Failed or blocked laps do not burn held-out days, and the judge may reuse those days because the builder must never read held-out content.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

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
- Separate judge must evaluate lap `20260606T070041Z` with planted-fake self-check, computer-use self-test, diff scan, held-out realday, real app proof, and different-family cross-check.
- Do not shrink M0 and do not count builder-visible raw audio or typed input as proof.
- If the lap is kept, continue product perimeter work, preferably improving direct app input inspectability when pending asks fill the surface or wiring another real hand path, while still running the whole-house realday every lap.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
