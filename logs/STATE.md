# STATE

Current milestone: M0, ugly floor. Latest judged lap `20260606T082329Z` was `FAKE`: the separate judge ran a held-out realday, found `act=45`, `ask=366`, `ignore=2523`, and verified no current-lap Calendar, Gmail, browser, or other external real-world artifact. It also found 31 apparent completions backed by internal `read_context`, not real app artifacts. M0 remains open until a fresh held-out real day produces a real verified artifact in a separate judge session.

Current builder lap:
- Lap `20260606T113648Z` is kept locally pending judge review.
- Builder change: `engine/anticipy_engine/core/orchestrator.py` now blocks action-like goals from reaching `goal_done` when all proof is support-only. Memory reads, memory writes, list-open-loop results, and screenshot-only browser reads can prove a step ran, but they cannot complete an external-action goal by themselves.
- Accepted action proof remains artifact-shaped proof such as API ids, message ids, event ids, draft ids, record ids, timestamps, or an explicit browser artifact marker.
- Builder verification for `20260606T113648Z`: focused guard checks passed, `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode, and the required builder-visible raw MP3 realday completed on raw audio id `2026-05-20_07_34_11` with `line_count=3228`, `act=28`, `ask=385`, `ignore=2815`, and `wall_seconds=1840.665`.
- This is builder-side evidence only. It is not judge proof and does not advance M0.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260606T082329Z.md`. Each kept proof includes planted-fake self-check, computer-use self-test, tamper scan, different-family OpenRouter cross-check, and a separate verdict. None verified an M0 real artifact.
- Judge proof for `20260606T070041Z` exists at `logs/verdicts/20260606T070041Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean for the target builder commit, a held-out MP3 ran end to end, Calendar and Gmail read-back/screenshots found no current-lap artifact, Gemini OpenRouter cross-check agreed with `FAKE`, and no held-out day rotated out.
- Judge proof for `20260606T082329Z` exists at `logs/verdicts/20260606T082329Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean for target builder commit `e062cdb` and later control-plane commits, a held-out MP3 ran end to end, Calendar and Gmail read-back/screenshots found no current-lap artifact, Gemini OpenRouter cross-check agreed with `FAKE`, and no held-out day rotated out.
- Gate verification after reverting `e062cdb`: `bash macapp/scripts/build_app.sh` passed and `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.
- Gate commits for `20260606T082329Z`: revert commit `b07a1d0`, proof/log commit `5cd8076`.
- Builder lap `20260606T113648Z` added an orchestrator final completion guard against support-only action completion; focused checks passed; `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode; required builder-visible raw realday completed with counts listed above. Judge verdict is pending.
- Amendment 2 is active: raw traces, `logs/last_realday.json`, transcript files, `.anticipy-data/`, and raw verdict JSON/JSONL are local-only and ignored. Builder-readable durable files contain verdicts, counts, proof links, and lessons only, not raw held-out transcript text.
- Boundary maintenance at `2026-06-06T09:13:41Z` rechecked Amendment 2 on disk and untracked ignored setup judge replay logs from git with `git rm --cached`, leaving the local copies in place.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs, builder-side acts, app UI inspection, DuckDuckGo searches, read-context proof, write-memory proof, channel-stub proof, stale eval artifacts, support-only internal proof, unjudged app input work, and unjudged completion-guard work are not judge-verified M0 proof.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Judge laps `20260606T020452Z`, `20260606T025532Z`, `20260606T060511Z`, and `20260606T070041Z` found Gmail read-only connector read-back returns `auth_status: pending`; UI screenshots were used for those verdicts, but a future Gmail artifact still needs connector read-back or a recorded scope gate.
- Separate judge for builder lap `20260606T113648Z` is pending.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/7 attempts verified, 0 percent.
- Latest judged held-out run: `20260606T082329Z`, `act=45`, `ask=366`, `ignore=2523`; verified external artifacts: 0; fake internal completions backed by read-context: 31.
- Latest builder-visible realday run: `20260606T113648Z`, `line_count=3228`, `act=28`, `ask=385`, `ignore=2815`, `wall_seconds=1840.665`; verified external artifacts: 0.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet. Generalization remains UNPROVEN.
- Drift siren: DRIFT is active. Builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. Under Amendment 2, a held-out day is burned only when it contributes to a milestone PASS. Failed or blocked laps do not burn held-out days, and the judge may reuse those days because the builder must never read held-out content.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.
- Lap `20260606T113648Z` ran builder-visible raw audio only in the builder session. The builder did not read holdout. The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

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

Next:
- Run the separate judge for `20260606T113648Z` on the kept builder commit. Do not mark M0 done unless the judge verifies a real external artifact.
- If the judge still finds no artifact, pivot from guard work to routing action tasks into API hands, the real browser agent hand, or explicit ask/needs-human.
- Do not shrink M0 and do not count builder-visible raw audio or internal proof as proof.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
