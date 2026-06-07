# STATE

Current milestone: M0, ugly floor. Latest judged lap `20260606T151119Z` was `FAKE`: the separate judge ran a held-out realday, found `line_count=1606`, `act=13`, `ask=176`, `ignore=1417`, and `wall_seconds=491.257`. The live system created one real Calendar artifact, but the artifact was semantically wrong and was deleted after judge verification. Correct real tasks verified: `0`. Wrong external actions verified: `1`. Builder commit `df47205` was reverted by that gate. M0 remains open.

Current unjudged builder lap: `20260607T011820Z` is kept on `autopilot/build` pending judge. It narrowed the last failure by requiring concrete Calendar times before any live `create_event` reaches Arcade. The planner prompt now supplies `CURRENT_LOCAL_TIME`, asks for `summary/start_datetime/end_datetime`, and says not to use capture time unless the user asked for now. The API hand now returns `needs_human` for live Calendar writes without concrete ISO-like `start_datetime` and `end_datetime`. Builder-visible realday completed with `line_count=3228`, `act=28`, `ask=385`, `ignore=2815`, and `wall_seconds=1422.806`. This is not proof. `judge_verdict=PENDING`.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260606T151119Z.md`. Each kept proof includes planted-fake self-check, computer-use self-test, tamper scan, different-family OpenRouter cross-check, and a separate verdict. None verified M0.
- Judge proof for `20260606T151119Z` exists at `logs/verdicts/20260606T151119Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, a held-out MP3 ran end to end, Calendar connector read-back and screenshot verified one current-lap `[Anticipy test]` event, the semantic check ruled the event wrong, the judge deleted it and confirmed post-delete read-back matched the event id zero times, Gmail screenshot found no sent message, and Gemini through OpenRouter agreed with `FAKE` after a tiny low-credit retry.
- Gate verification after reverting `df47205`: `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.
- Current lap local checks passed: focused Calendar guard check, `test_api_hand.py`, Python compile for edited files, and `bash scripts/run_suite.sh` 29/29. These are builder-side checks only.
- Amendment 2 is active: raw traces, `logs/last_realday.json`, transcript files, `.anticipy-data/`, and raw verdict JSON/JSONL are local-only and ignored. Builder-readable durable files contain verdicts, counts, proof links, and lessons only, not raw held-out transcript text.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs, builder-side acts, app UI inspection, DuckDuckGo searches, read-context proof, write-memory proof, channel-stub proof, stale eval artifacts, support-only internal proof, wrong real artifacts, unjudged app input work, unjudged completion-guard work, reverted planner-filtering work, reverted real-action-routing work, and the current unjudged Calendar guard are not judge-verified M0 proof.

Pending gates:
- No current hard human gate blocks all work.
- OpenRouter credit is very low. The `20260606T151119Z` judge needed a tiny different-family retry after larger cross-check attempts returned HTTP 402. If a future required cross-check cannot run because the key is unfunded or prompt-limited, that becomes a human money/key gate in `PENDING_FOR_OMAR.md`.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Several judge laps found Gmail read-only connector read-back returns `auth_status: pending`; UI screenshots were used for those verdicts, but a future Gmail artifact still needs connector read-back or a recorded scope gate.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on amended fresh unseen attempts: 0/10 verified, 0 percent.
- Latest judged held-out run: `20260606T151119Z`, `act=13`, `ask=176`, `ignore=1417`; correct real tasks verified: 0; real external artifacts verified: 1 but semantically wrong and cleaned up; wrong external actions verified: 1.
- Latest unjudged builder-visible realday run: `20260607T011820Z`, `line_count=3228`, `act=28`, `ask=385`, `ignore=2815`, `wall_seconds=1422.806`. Cost is not isolated from the cumulative local scorecard.
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
- The `20260606T151119Z` real-action-routing slice was not proven by the judge and was reverted. A real Calendar artifact with the wrong time is a wrong external action, not progress. Do not use capture timestamps as requested event times unless the user explicitly asked for now; parse future-relative time semantically or abstain.

Next:
- Run the separate judge for builder lap `20260607T011820Z`. The judge must verify whether the Calendar guard prevents wrong artifacts and whether any real task is correctly completed on held-out audio.
- If the judge still finds no correct artifact, keep the failed slice isolated on `autopilot/build`, revert if required by the gate, and pivot to propagating a real event-time anchor from the realday source into planning or to explicit ask behavior.
- Keep the perimeter constraint active and do not spend more than 3 consecutive inference or brain laps without advancing M1, M2, M3, or M5.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
