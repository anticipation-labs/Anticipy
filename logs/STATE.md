# STATE

Current milestone: M0, ugly floor. Latest judged lap `20260606T124709Z` was `FAKE`: the separate judge ran a held-out realday, found `act=13`, `ask=176`, `ignore=1417`, verified no current-lap Calendar, Gmail, browser, or other external real-world artifact, and found all 13 act goals marked `done` with zero steps and zero proof keys. That failed slice was reverted. Latest builder lap `20260606T151119Z` is `PENDING_JUDGE`: it completed the builder-visible raw transcript with real action routing fixes, but M0 remains open until the separate judge verifies a current-lap real artifact on a held-out day.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260606T124709Z.md`. Each kept proof includes planted-fake self-check, computer-use self-test, tamper scan, different-family OpenRouter cross-check, and a separate verdict. None verified an M0 real artifact.
- Judge proof for `20260606T124709Z` exists at `logs/verdicts/20260606T124709Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean for builder commit `7a8ddc9`, a held-out MP3 ran end to end, Calendar connector read-back plus Calendar/Gmail screenshots found no current-lap artifact, Gemini OpenRouter cross-check agreed with `FAKE`, and no held-out day rotated out.
- Builder lap `20260606T151119Z` fixed zero-step completions, stopped action tasks from degrading into blind browser search, added conservative app-backed fallback planning, normalized Calendar write args to `summary/start_datetime/end_datetime`, tagged build/test Calendar events, blocked non-self email and third-party message writes, mocked SMS during build/test, and surfaced low-credit OpenRouter planner failures instead of silently producing empty plans.
- Focused builder checks for fallback routing, Calendar normalization, build/test API safety, SMS safety, and live OpenRouter fallback passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode after the `20260606T151119Z` changes.
- Builder-visible raw transcript run for `20260606T151119Z` completed with `line_count=3228`, `act=26`, `ask=387`, `ignore=2815`, `goal_outcomes success=7 waiting=18`, `wall_seconds=100.613`, and `cost_usd=0.36`. This is builder-side evidence only, not proof.
- Amendment 2 is active: raw traces, `logs/last_realday.json`, transcript files, `.anticipy-data/`, and raw verdict JSON/JSONL are local-only and ignored. Builder-readable durable files contain verdicts, counts, proof links, and lessons only, not raw held-out transcript text.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs, builder-side acts, app UI inspection, DuckDuckGo searches, read-context proof, write-memory proof, channel-stub proof, stale eval artifacts, support-only internal proof, unjudged app input work, unjudged completion-guard work, reverted planner-filtering work, and pending builder successes are not judge-verified M0 proof.

Pending gates:
- Separate judge is pending for lap `20260606T151119Z` after the builder commit is created.
- OpenRouter credit is very low. A builder raw run failed once on a 402 prompt-budget error before fallback-first routing. If the separate judge's different-family cross-check cannot run because the key is unfunded or prompt-limited, that becomes a human money/key gate in `PENDING_FOR_OMAR.md`.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Several judge laps found Gmail read-only connector read-back returns `auth_status: pending`; UI screenshots were used for those verdicts, but a future Gmail artifact still needs connector read-back or a recorded scope gate.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/9 attempts verified, 0 percent.
- Latest judged held-out run: `20260606T124709Z`, `act=13`, `ask=176`, `ignore=1417`; verified external artifacts: 0; fake internal completions with no steps and no proof keys: 13.
- Latest builder-visible realday run: `20260606T151119Z`, `line_count=3228`, `act=26`, `ask=387`, `ignore=2815`, `goal_outcomes success=7 waiting=18`, `wall_seconds=100.613`; verified external artifacts: 0 until judge says otherwise.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet. Generalization remains UNPROVEN.
- Drift siren: DRIFT is active. Builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
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
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, or any support-only proof as completed real-world actions for tasks that require sending, booking, creating, buying, posting, submitting, calling, or changing an external artifact.
- Do not let the planner type a whole task into the browser search bar as a substitute for decomposition. Explicit information lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not allow stale eval-literal goals such as old M0 proof Calendar/Gmail tasks, previous-lap ids, or old sent-mail subjects to contaminate held-out plans.
- The `20260606T070041Z` and `20260606T082329Z` app input slices were not proven by the judge and were reverted. They cannot be claimed.
- The `20260606T113648Z` completion-guard slice was not proven by the judge and was reverted. Do not spend another lap on guard-only proof. Pivot to real action routing through API hands, the real browser agent hand, or explicit ask/needs-human.
- The `20260606T124709Z` live-planner filtering slice was not proven by the judge and was reverted. Do not spend another lap on prompt/filter-only proof. Fix real action routing or wait/ask behavior.
- OpenRouter low credit can produce truncated prose or 402 prompt-budget errors. Do not assume JSON mode is reliable under credit pressure; use deterministic app-backed routing for clear actions and treat real key exhaustion as a human gate.

Next:
- Commit lap `20260606T151119Z` on `autopilot/build`.
- Run the separate judge for `20260606T151119Z` with `AUTOPILOT_BUILDER_COMMIT` set to the resulting commit.
- Apply the normal gate from `autopilot/04_LOOP.md`: keep only if the judge rules REAL, the different-family cross-check agrees, the diff scan is clean, and no tripwire fires. Otherwise revert and log.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
