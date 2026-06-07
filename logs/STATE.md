# STATE

Current milestone: M1, real front door. M1 means a clean profile can download a `.app` from the project's public front door at `anticipy.ai/app`, launch it, and see the live surface. M0 clean floor is proven, but the product is not done until a stranger can download, onboard, connect their own apps, and get a real task done.

Latest judged lap: `20260607T032947Z` was `REAL`. The separate judge ran a typed, fully time-grounded, safe, reversible Calendar instruction through the live `/event` endpoint. It verified the real Calendar artifact by connector read-back and Google Calendar UI screenshot, confirmed no Gmail sent-message false action, deleted the test event, verified post-delete cleanup, and got Gemini OpenRouter agreement with the Codex judge. Proof: `logs/verdicts/20260607T032947Z.md`.

Latest kept build slice: `20260607T032738Z` added deterministic planning for explicit fully grounded Calendar event instructions, emitted real `create_event` steps with `summary`, `start_datetime`, `end_datetime`, and timezone, and made empty plans fail instead of marking zero-step goals done. Focused checks passed and `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. It is now kept because the `20260607T032947Z` judge proved it on a real Calendar artifact.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The stranger path is not proven. There is still no real public download, onboarding, self-connect flow, or full stranger task completion.
- M1 is not proven until the judge downloads and launches the app from the public front door.

Pending gates:
- No hard human gate blocks all work.
- OpenRouter credit is very low. Recent judges used tiny Gemini cross-checks successfully. If a required different-family cross-check cannot run because the key is unfunded or prompt-limited, record a human money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked paths.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: the clean M0 reality rate improved from 0/2 to 1/3 on real judge proof. Do not advance future milestones from builder-side evidence.

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
- Gate and commit the `20260607T032947Z` proof/log package.
- Advance to M1. Inspect the current `app/` front door and deployment/package scripts, then build the smallest real public download slice.
- Continue on `autopilot/build`. Merge proven work to `main` only after the gate commit is clean.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
