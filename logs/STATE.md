# STATE

Current milestone: M1, real front door. M1 means a clean profile can download a `.app` from the public front door at `anticipy.ai/app`, launch it, and see the live surface. M0 clean floor is proven once, but the product is not done until a stranger can download, onboard, connect their own apps, and get a real task done.

Latest build slice: `20260607T035948Z` was committed on `autopilot/build` as `7b430a4`. It added a local packaging path for the executor Mac app, generated `public/downloads/Anticipy-mac.zip` plus SHA-256, replaced the local placeholder page with a real Mac download page, and updated the autopilot prompts so M1 is judged as a front-door download instead of rerunning M0 Calendar. It also recorded that production `anticipy.ai` is Vercel project `anticipy`, while this repo is linked to `anticipy-executor-working`.

Latest judge attempt: `20260607T035948Z` against builder commit `7b430a4` stopped before verdict because the separate Codex CLI judge hit the ChatGPT Codex usage limit. The CLI reported: try again at 10:50 PM PDT, with purchase as the other option. Spending money is a hard stop, so no purchase was attempted. No M1 proof is claimed.

Latest judged lap with verdict: `20260607T032947Z` was `REAL`. The separate judge ran a typed, fully time-grounded, safe, reversible Calendar instruction through the live `/event` endpoint. It verified the real Calendar artifact by connector read-back and Google Calendar UI screenshot, confirmed no Gmail sent-message false action, deleted the test event, verified post-delete cleanup, and got Gemini OpenRouter agreement with the Codex judge. Proof: `logs/verdicts/20260607T032947Z.md`.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Build-side evidence, not proof:
- `npm run package:mac` built, ad-hoc signed, zipped, and checksummed the executor Mac app.
- Extracted `public/downloads/Anticipy-mac.zip` contains an executable app and passes `codesign --verify`.
- `spctl --assess` rejects the local app because no Developer ID certificate is installed.
- `npm run build` passed.
- Browser opened the local page and the local zip endpoint returned 200.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode.

Not proven:
- M1 is not proven until the separate judge downloads and launches the public app from `https://www.anticipy.ai/app`.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public download alone is not onboarding, self-connect, or stranger task completion.

Pending gates:
- Temporary gate: the separate Codex CLI judge cannot start until the ChatGPT Codex usage reset at 10:50 PM PDT on 2026-06-06. Purchase was offered by the CLI but was not used because spending money is a hard stop.
- No hard human gate blocks all work after the quota reset.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Current builds can be ad-hoc signed, but full zero-warning stranger install needs Developer ID and notarization.
- OpenRouter credit is very low. Recent judges used tiny Gemini cross-checks successfully. If a required different-family cross-check cannot run because the key is unfunded or prompt-limited, record a human money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked paths.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/0 verified, pending first M1 verdict. The startup-limited judge attempt does not count as a product failure or pass.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: do not advance M1 from local packaging evidence. The separate judge must verify the public front door.

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
- Do not deploy this executor worktree to the production `anticipy` Vercel project blindly. The production app has many routes and belongs to the older `Anticipy-DEV-FINAL` source tree.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, empty-plan `goal_done`, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- After the Codex usage reset, rerun the separate M1 judge with `AUTOPILOT_LAP=20260607T035948Z AUTOPILOT_BUILDER_COMMIT=7b430a4 autopilot/judge_lap`, preferably with Supabase MCP disabled if the known startup issue recurs.
- Gate the result. If REAL, merge proven work to `main`; if FAKE or BLOCKED, revert unproven code or log the real gate and continue on unblocked perimeter work.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
