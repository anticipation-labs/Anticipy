# STATE

Current milestone: M0, ugly floor. Latest builder lap `20260606T124709Z` is pending judge review. It added a live-planner routing slice so OpenRouter planning sees only artifact-capable user-task intents, filters out internal support intents, and leaves empty live plans waiting instead of completing. The latest judged lap remains `20260606T113648Z`, verdict `FAKE`: the separate judge ran a held-out realday, found `act=13`, `ask=176`, `ignore=1417`, verified no current-lap Calendar, Gmail, browser, or other external real-world artifact, and found 13 internal `goal_done` entries with no artifact-shaped proof. M0 remains open until a fresh held-out real day produces a real verified artifact in a separate judge session.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260606T113648Z.md`. Each kept proof includes planted-fake self-check, computer-use self-test, tamper scan, different-family OpenRouter cross-check, and a separate verdict. None verified an M0 real artifact.
- Judge proof for `20260606T082329Z` exists at `logs/verdicts/20260606T082329Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, a held-out MP3 ran end to end, Calendar/Gmail read-back plus screenshots found no current-lap artifact, Gemini OpenRouter cross-check agreed with `FAKE`, and no held-out day rotated out.
- Judge proof for `20260606T113648Z` exists at `logs/verdicts/20260606T113648Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean for builder commit `7623805`, a held-out MP3 ran end to end, Calendar connector read-back plus Calendar/Gmail screenshots found no current-lap artifact, Gemini OpenRouter cross-check agreed with `FAKE`, and no held-out day rotated out.
- Builder lap `20260606T124709Z` added live planner routing to keep internal support intents out of OpenRouter user-task plans. A focused fake-live planner check passed, `py_compile` passed, `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode, and the required builder-visible raw MP3 realday completed with `line_count=3228`, `act=28`, `ask=385`, `ignore=2815`, and `wall_seconds=1845.675`. This is not judge proof.
- Gate verification after reverting `7623805`: `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.
- Gate commits for `20260606T113648Z`: revert commit `84fe1d0`; proof/log commit `f66a0ae`.
- Amendment 2 is active: raw traces, `logs/last_realday.json`, transcript files, `.anticipy-data/`, and raw verdict JSON/JSONL are local-only and ignored. Builder-readable durable files contain verdicts, counts, proof links, and lessons only, not raw held-out transcript text.
- Boundary maintenance at `2026-06-06T09:13:41Z` rechecked Amendment 2 on disk and untracked ignored setup judge replay logs from git with `git rm --cached`, leaving the local copies in place.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs, builder-side acts, app UI inspection, DuckDuckGo searches, read-context proof, write-memory proof, channel-stub proof, stale eval artifacts, support-only internal proof, unjudged app input work, unjudged completion-guard work, and unjudged live-planner routing work are not judge-verified M0 proof.

Pending gates:
- No current hard human gate blocks M0.
- Separate judge review is pending for builder lap `20260606T124709Z`.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Several judge laps found Gmail read-only connector read-back returns `auth_status: pending`; UI screenshots were used for those verdicts, but a future Gmail artifact still needs connector read-back or a recorded scope gate.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/8 attempts verified, 0 percent.
- Latest judged held-out run: `20260606T113648Z`, `act=13`, `ask=176`, `ignore=1417`; verified external artifacts: 0; fake internal completions with no artifact-shaped proof: 13.
- Latest builder-visible realday run: `20260606T124709Z`, `line_count=3228`, `act=28`, `ask=385`, `ignore=2815`, `wall_seconds=1845.675`; verified external artifacts: 0, pending judge.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet. Generalization remains UNPROVEN.
- Drift siren: DRIFT is active. Builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. Under Amendment 2, a held-out day is burned only when it contributes to a milestone PASS. Failed or blocked laps do not burn held-out days, and the judge may reuse those days because the builder must never read held-out content.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.
- Lap `20260606T124709Z` ran builder-visible raw audio only in the builder session. The separate judge has not yet ruled. The builder did not read holdout. The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Do not treat a verdict inventory list as proof that every listed holdout day was read or burned.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, or any support-only proof as completed real-world actions for tasks that require sending, booking, creating, buying, posting, submitting, calling, or changing an external artifact.
- Do not let the planner type a whole task into the browser search bar as a substitute for decomposition. Explicit information lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not allow stale eval-literal goals such as old M0 proof Calendar/Gmail tasks, previous-lap ids, or old sent-mail subjects to contaminate held-out plans.
- The `20260606T070041Z` and `20260606T082329Z` app input slices were not proven by the judge and were reverted. They cannot be claimed.
- The `20260606T113648Z` completion-guard slice was not proven by the judge and was reverted. Do not spend another lap on guard-only proof. Keep pushing action tasks into API hands first, then the real browser agent hand, else explicit ask/needs-human.

Next:
- Run the separate judge for builder lap `20260606T124709Z`.
- Do not shrink M0 and do not count builder-visible raw audio or internal proof as proof.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
