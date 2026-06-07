# STATE

Current milestone: M0, clean floor. M0 is a typed, fully time-grounded task through the live system. Done means the separate judge verifies one real, correct, safe, reversible artifact in the real app with connector read-back where available, screenshot proof, and cleanup after verification.

Latest judged lap: `20260607T024251Z` was `FAKE`. The judge supplied a typed, fully time-grounded Calendar instruction with a unique `[Anticipy test]` title. The live system returned `decision=ask` with reason `cannot confirm safe -> fail-safe ask`, so no Calendar artifact was created. Calendar connector read-back matched `0` events, Calendar UI search found no event, and the different-family OpenRouter cross-check agreed with `FAKE`. M0 remains open.

Latest stopped lap: `20260607T011820Z` has no verdict. Its separate judge was cleanly stopped after tens of minutes on the old audio-first path. No held-out day was burned and no proof is claimed. The Calendar concrete-time guard from that slice remains a safety floor, but a guard or abstention does not advance M0.

Current kept infrastructure:
- Amendment 3 control plane is on disk.
- Sidecar transcript caching is in `engine/anticipy_engine/capture/transcribe.py`.
- `/event` accepts metadata.
- `scripts/realday.sh` passes `observed_at`, capture start, transcript offsets, and timezone into the engine.
- `ProactiveEngine` includes that clock context in the goal description used by the planner.
- Build and judge prompts use clean typed M0 before audio.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260607T024251Z.md`. None verified M0.
- Current control slice checks passed: shell syntax for `scripts/realday.sh`, `autopilot/build_lap`, and `autopilot/judge_lap`; Python compile for edited files; cached transcript check on the existing builder-visible sidecar; `bash scripts/run_suite.sh` 29/29; stub/mock clean-M0 harness smoke in seconds with `observed_at` metadata present.
- Post-verdict `bash scripts/run_suite.sh` passed 29/29.
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
- Fix positive Calendar completion for safe, reversible, fully time-grounded `[Anticipy test]` tasks. The system must create the correct Calendar artifact through the live task loop.
- Do not add another refusal guard. The failure is ask-only behavior on a safe clean task.
- Run the next separate judge on clean typed M0 again.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, and ask-only behavior are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
