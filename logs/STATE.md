# STATE

Current milestone: M1, real front door. M1 means a clean profile can download a `.app` from the public front door at `anticipy.ai/app`, launch it, and see the live surface. M0 clean floor is proven once, but the product is not done until a stranger can download, onboard, connect their own apps, and get a real task done.

Latest judged lap: `20260607T035948Z` was `FAKE`. The separate M1 judge passed planted-fake self-check, computer-use self-test, tamper scan, and different-family OpenRouter cross-check. It verified that production `/download` returns a 2.5 GB DMG and the mounted DMG contains `Anticipy.app`, but clean `/app` showed an account form rather than a direct download, `codesign` and `spctl` failed with resource-signature errors, and launching the public app exposed only a macOS microphone permission prompt rather than a readable Anticipy live surface. Proof: `logs/verdicts/20260607T035948Z.md`.

Latest build lap: `20260607T064745Z` is pending separate judge. It made the local Swift app open on the live Main surface, changed bundle metadata to `ai.anticipy.app` version `1.0.0`, built successfully, passed `codesign --verify` after ad-hoc signing, failed `spctl` because no Developer ID identity exists, and was visually checked with Computer Use from the rebuilt bundle. Public checks still showed the production `/app` and DMG paths are separate from this local source slice.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Build-side evidence, not proof:
- Local app launch surface is better: the rebuilt app opens directly to Main and Computer Use saw the live surface.
- The reverted M1 slice showed a local executor app can be packaged as a zip and served from the local Next app, but the separate judge proved this does not prove the production public front door.
- Production `https://www.anticipy.ai/app` belongs to Vercel project `anticipy`, not this repo's linked `anticipy-executor-working` project.
- Production `/download` and canonical `/dl/Anticipy_1.0.0_aarch64.dmg` still need a release-path fix and clean judge verification; builder header checks are not proof.

Not proven:
- M1 is not proven. The actual production public app must launch to a readable live Anticipy surface from a clean front-door path.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public download alone is not onboarding, self-connect, or stranger task completion.

Pending gates:
- No hard human gate blocks all work.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Current builds can be ad-hoc signed, but full zero-warning stranger install needs Developer ID and notarization. The judge also found the production DMG app has a resource-signature failure, which must be fixed or explicitly routed through a safe install flow before M1 can pass.
- OpenRouter credit is very low. Paid Gemini cross-check hit HTTP 402 during the M1 judge; the judge used a free Google-family model that agreed with `FAKE`. If all required different-family cross-checks become unavailable, record a human money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked paths.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/1 verified, 0 percent, with lap `20260607T064745Z` pending judge.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: do not advance M1 from local app launch, local packaging, header evidence, or authenticated-profile observations. The separate judge must see a launched live surface from the production front door.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Treating the local executor Next page or local zip as proof for production `anticipy.ai/app`.
- Blindly deploying this executor worktree to production `anticipy`, because production has a larger app and belongs to the older `Anticipy-DEV-FINAL` source tree.
- Treating authenticated-owner Chrome observations as clean stranger proof.
- Treating public headers, local app launch, or local screenshots as M1 proof without the separate judge.
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, empty-plan `goal_done`, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- Commit lap `20260607T064745Z`, then run the separate M1 judge against that builder commit.
- If the judge fails because production has not received the fixed app/runtime, gate it honestly and pivot to the actual production release path.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
