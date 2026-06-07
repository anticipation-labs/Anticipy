# STATE

Current milestone: M0, clean floor. M0 is now a typed, fully time-grounded task through the live system, not messy audio. Done means the separate judge verifies one real, correct, safe, reversible artifact in the real app with connector read-back where available, screenshot proof, and cleanup after verification.

Latest judged lap: `20260606T151119Z` was `FAKE`. The separate judge verified one real Calendar artifact, but it was semantically wrong and was deleted after verification. Correct real tasks verified: `0`. Wrong external actions verified: `1`.

Latest stopped lap: `20260607T011820Z` has no verdict. Its separate judge was cleanly stopped after tens of minutes on the old audio-first path. No held-out day was burned and no proof is claimed. The Calendar concrete-time guard from that slice remains a safety floor, but a guard or abstention does not advance M0.

Current unjudged control slice: `20260607T024251Z` applies Amendment 3. Sidecar transcript caching is in `engine/anticipy_engine/capture/transcribe.py`. `/event` accepts metadata. `scripts/realday.sh` passes `observed_at`, capture start, transcript offsets, and timezone into the engine. `ProactiveEngine` includes that clock context in the goal description used by the planner. Build and judge prompts now use clean typed M0 before audio.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260606T151119Z.md`. None verified M0.
- Gate verification after reverting `df47205`: `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.
- Current control slice checks passed: shell syntax for `scripts/realday.sh`, `autopilot/build_lap`, and `autopilot/judge_lap`; Python compile for edited files; cached transcript check on the existing builder-visible sidecar; `bash scripts/run_suite.sh` 29/29; stub/mock clean-M0 harness smoke in seconds with `observed_at` metadata present.
- No M0 real task is proven. Builder-side checks, stopped judge work, guard-only work, abstention, cached transcript plumbing, and stub/mock clean-M0 smoke are not judge proof.

Pending gates:
- No current hard human gate blocks all work.
- OpenRouter credit is very low. If a required different-family cross-check cannot run because the key is unfunded or prompt-limited, that becomes a human money/key gate in `PENDING_FOR_OMAR.md`.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on amended attempts before clean M0: 0/10 verified, 0 percent.
- Clean typed M0 judge attempts: 0/0 so far.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet. Generalization remains UNPROVEN.
- Drift siren: DRIFT remains active for the old audio path. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is now sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- Commit the Amendment 3 control/code slice.
- Run the separate judge on the clean typed M0 path against the current commit. The judge must create a safe unique `[Anticipy test]` typed Calendar task, run it through the live system, verify the real artifact by connector read-back and screenshot, delete it after verification, run the different-family cross-check, and write the verdict.
- If the judge verifies a correct artifact with clean oversight, M0 clean floor can be kept. If not, do not advance and fix positive completion capability.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards and abstention are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
