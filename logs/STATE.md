# STATE

Current milestone: M1, real front door. M1 means a clean profile can download a `.app` from the public front door at `anticipy.ai/app`, launch it, and see the live surface. M0 clean floor is proven once, but the product is not done until a stranger can download, onboard, connect their own apps, and get a real task done.

Latest judged lap: `20260607T064745Z` was `FAKE`. The separate M1 judge passed planted-fake self-check, computer-use self-test, tamper scan, and different-family OpenRouter cross-check. It verified that clean public `/app` still shows account creation and no direct download link, the public DMG downloads and mounts, but `codesign` and `spctl` fail with resource-signature errors and the launched public app shows only a macOS microphone permission prompt rather than a readable live Anticipy surface. Proof: `logs/verdicts/20260607T064745Z.md`.

Current build lap: `20260607T075335Z` is unjudged and has `judge_verdict=PENDING`. It worked in the production-linked source tree at `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`, not the local executor placeholder front door. Build-side evidence only:
- The Tauri app now calls `show_popover(app.handle())` on launch and no longer starts the Rust microphone permission bootstrap automatically.
- `desktop/scripts/tauri.mjs` now ad-hoc signs the app before DMG creation and writes all plausible DMG output paths instead of returning after the first one.
- `bash scripts/build_dmg.sh` completed after those fixes.
- The regenerated local root DMG hash is `ddd20a490ac6a301fc9f6d321fd4ec53e6d74711364929171c869882119c7692`.
- The app inside the mounted local root DMG passed `codesign --verify --deep --strict --verbose=2` and `codesign -dvvv` reported `Sealed Resources version=2`.
- `spctl --assess --type execute -vv` still rejected the app because it is ad-hoc signed, not Developer ID signed or notarized.
- Public `https://www.anticipy.ai/app`, `/download`, and `/dl/Anticipy_1.0.0_aarch64.dmg` still serve the old public artifact. The rebuilt DMG is not deployed.
- Mounted-DMG GUI launch showed the Anticipy popover, but screenshots were contaminated by unresolved microphone permission prompts already present in Safari/Chrome. This is not clean launch proof.

Gate status: no hard human gate blocks all work. Apple Developer ID signing and notarization remain unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Full no-warning stranger install still needs Developer ID/notarization. OpenRouter credit is very low; if all required different-family cross-checks become unavailable, record a money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked paths. Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- M1 is not proven. The actual production public app must launch to a readable live Anticipy surface from a clean front-door path.
- The rebuilt local production-linked DMG is not public and has not been judged.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public download alone is not onboarding, self-connect, or stranger task completion.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/2 verified, 0 percent.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: active. Builder-owned tests remain green while M1 reality pass rate is 0 percent. Do not advance M1 from local app launch, local packaging, public headers, authenticated-owner Chrome observations, or screenshots without the separate judge seeing the clean production front door launch a readable live surface.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Treating the local executor Next page, local zip, or local Swift app launch as proof for production `anticipy.ai/app`.
- Blindly deploying this executor worktree to production `anticipy`, because production has a larger app and belongs to the older `Anticipy-DEV-FINAL` source tree.
- Running production `scripts/ship.sh` as-is from `Anticipy-DEV-FINAL` in this lap, because it pushes to `origin main`; use a safe non-push publish path or explicitly isolate the publish step.
- Treating authenticated-owner Chrome observations as clean stranger proof.
- Treating public headers, local app launch, local screenshots, or app activation by name as M1 proof without the separate judge.
- Treating the current 2.5 GB public DMG as a healthy normal verifier path. It completed, but it made M1 judges take tens of minutes.
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, empty-plan `goal_done`, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- Continue M1 with the production-linked source path. Cleanly isolate and remove any remaining automatic microphone prompt before the visible surface.
- Rebuild and launch from a clean UI state so the local mounted DMG shows the readable live surface without prompt contamination.
- Publish the corrected DMG to the real public artifact path only after the local mounted DMG passes clean launch checks; do not push from this executor worktree.
- Keep the public artifact small enough that a normal M1 judge can complete in minutes, or document why the verifier must download the full artifact.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
