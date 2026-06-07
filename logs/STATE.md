# STATE

Current milestone: M0, clean floor. M0 is a typed, fully time-grounded task through the live system. Done means the separate judge verifies one real, correct, safe, reversible artifact in the real app with connector read-back where available, screenshot proof, different-family cross-check, clean diff scan, and cleanup after verification.

Latest judged lap: `20260607T030839Z` was `FAKE`. The judge ran a typed, fully time-grounded Calendar task through the live `/event` endpoint. The system returned `decision=act`, but the resulting goal was marked `done` with zero steps and empty proof. Calendar connector read-back matched `0` events, Google Calendar UI search found no event, Gmail Sent search found no message, and the different-family OpenRouter/Gemini cross-check agreed with `FAKE`. Failed builder commit `330ff05` was reverted by `82447bc`. M0 remains open.

Latest stopped lap: `20260607T030217Z` has no verdict. Its separate judge attempt was stopped after repeated startup/runtime warnings and no final verdict markdown. No held-out day was used or burned, and no proof is claimed. The replacement judge `20260607T030839Z` produced the current verdict.

Current kept infrastructure:
- Amendment 3 control plane is on disk.
- Sidecar transcript caching is in `engine/anticipy_engine/capture/transcribe.py`.
- `/event` accepts metadata.
- `scripts/realday.sh` passes `observed_at`, capture start, transcript offsets, and timezone into the engine.
- `ProactiveEngine` includes that clock context in the goal description used by the planner.
- Build and judge prompts use clean typed M0 before audio.
- Calendar concrete-time guard remains a safety floor: live `create_event` jobs without concrete `start_datetime` and `end_datetime` are blocked before Arcade execution.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260607T030839Z.md`. None verified M0.
- Post-revert `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.
- No M0 real task is proven. Builder-side checks, stopped judge work, guard-only work, abstention, cached transcript plumbing, and stub/mock clean-M0 smoke are not judge proof.

Pending gates:
- No current hard human gate blocks all work.
- OpenRouter credit is very low. The latest judge required a tiny Gemini cross-check path after larger OpenRouter cross-checks failed. If a required different-family cross-check cannot run because the key is unfunded or prompt-limited, that becomes a human money/key gate in `PENDING_FOR_OMAR.md`.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on amended attempts before clean M0: 0/10 verified, 0 percent.
- Clean typed M0 judge attempts: 0/2 verified, 0 percent.
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
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, empty-plan `goal_done`, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- Fix the empty-plan completion path. An action goal with zero planned steps must never be marked done.
- For safe clean typed Calendar tasks, make the live planner/orchestrator produce a real `create_event` job with concrete `summary`, `start_datetime`, and `end_datetime`, or fail/wait loudly.
- Do not add another refusal-only guard. The next milestone attempt must create a real correct artifact verified by the judge.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
