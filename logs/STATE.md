# STATE

Current milestone: M0, clean floor. M0 is a typed, fully time-grounded task through the live system. Done means the separate judge verifies one real, correct, safe, reversible artifact in the real app with connector read-back where available, screenshot proof, different-family cross-check, clean diff scan, and cleanup after verification.

Latest build slice: `20260607T030012Z` is `NOT_JUDGED_BUILD_SLICE`. It fixed the generic harm-line gap from clean M0 lap `20260607T024251Z`: explicit self-owned Calendar event or entry creation now classifies as reversible `calendar_event` instead of unclassified ask. Calendar invitations are binding send-like asks, and public calendar events are public asks. Focused harm-line and proactive route checks passed, edited Python compiled, and `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is not M0 proof.

Latest judged lap: `20260607T024251Z` was `FAKE`. The judge supplied a typed, fully time-grounded Calendar instruction with a unique `[Anticipy test]` title. The live system returned `decision=ask` with reason `cannot confirm safe -> fail-safe ask`, so no Calendar artifact was created. Calendar connector read-back matched `0` events, Calendar UI search found no event, and the different-family OpenRouter cross-check agreed with `FAKE`. M0 remains open.

Latest stopped lap: `20260607T011820Z` has no verdict. Its separate judge was cleanly stopped after tens of minutes on the old audio-first path. No held-out day was burned and no proof is claimed. The Calendar concrete-time guard from that slice remains a safety floor, but a guard or abstention does not advance M0.

Current kept infrastructure:
- Amendment 3 control plane is on disk.
- Sidecar transcript caching is in `engine/anticipy_engine/capture/transcribe.py`.
- `/event` accepts metadata.
- `scripts/realday.sh` passes `observed_at`, capture start, transcript offsets, and timezone into the engine.
- `ProactiveEngine` includes that clock context in the goal description used by the planner.
- Build and judge prompts use clean typed M0 before audio.
- Harm-line admits explicit safe self-owned Calendar event creation while still asking on invitations and public event creation.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260607T024251Z.md`. None verified M0.
- Current build-side checks passed: `engine/scripts/test_harmline.py`, `engine/scripts/test_proactive.py`, Python compile for `engine/anticipy_engine/proactive/harm.py`, and `bash scripts/run_suite.sh` 29/29.
- No M0 real task is proven. Builder-side checks, stopped judge work, guard-only work, abstention, cached transcript plumbing, and stub/mock clean-M0 smoke are not judge proof.

Pending gates:
- No current hard human gate blocks all work.
- OpenRouter credit is very low. The latest judge needed a tiny cross-check retry after larger requests returned HTTP 402. If a required different-family cross-check cannot run because the key is unfunded or prompt-limited, that becomes a human money/key gate in `PENDING_FOR_OMAR.md`.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on amended attempts before clean M0: 0/10 verified, 0 percent.
- Clean typed M0 judge attempts: 0/1 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet. Generalization remains UNPROVEN.
- Drift siren: DRIFT remains active. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- Commit the build slice for `20260607T030012Z`.
- Run the separate clean M0 judge again. The system must create the correct Calendar artifact through the live task loop.
- Do not add another refusal guard. The next result must be a real correct artifact verified by the judge.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, and ask-only behavior are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
