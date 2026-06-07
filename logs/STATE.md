# STATE

Current milestone: M1, real front door. M1 means a clean profile can download a Mac app from the public front door at `anticipy.ai/app`, launch it, and see the live Anticipy surface. M0 clean floor is proven once, but the product is not done until a stranger can download, onboard, connect their own apps, and get a real task done.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed the planted-fake self-check, passed the computer-use self-test, scanned builder commit `76fc00d`, and found no tamper. It opened the clean public front door, downloaded the public 2.5 GB DMG, mounted it, and launched the public app. The public app failed M1 because `codesign --verify --strict` and `spctl --assess` failed with `code has no resources but signature indicates they must be present`, and launch produced an invisible app process with zero windows instead of a readable live Anticipy surface. The different-family Gemini cross-check agreed with `FAKE`. Proof: `logs/verdicts/20260607T114534Z.md`.

Pending unjudged builder slice: lap `20260607T131802Z` produced production-linked source commit `ccc96264` on `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` branch `rebuild/spine-clean`. It fixes the public `/app` source gate, app bundle resource signing before DMG creation, launch surface visibility, owner/eval literals in packaged paths, bridge screenshot home paths, and dirty-tree extension packaging. Local checks passed: changed Python compile, `node --check`, `plutil`, `git diff --check`, `cargo check`, `npm run build`, `bash scripts/build_dmg.sh`, regenerated zip literal scan, mounted-DMG `codesign --verify --strict`, and screenshot `/tmp/anticipy-m1-launch-after-wait.png` showing a readable Anticipy surface. This is build-side evidence only. The canonical public `anticipy.ai/app` and R2 DMG have not been judge-verified from this commit, and the separate Codex CLI runner is currently usage-limited.

Gate status: no hard human gate blocks all work. The failed builder commit `76fc00d` was reverted by `969218d` and must not be merged to `main`. Post-revert `bash macapp/scripts/build_app.sh` passed, and `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. The failed lap `20260607T075335Z` remains reverted by `d80f0ce`, with its failed production-linked diff preserved as `stash@{0}: failed lap 20260607T075335Z m1 package slice` in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`. The pending production commit `ccc96264` is not M1 proof and must not be represented as done until the separate judge verifies the real public front door.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Build-side evidence, not proof:
- Pending production-linked source commit `ccc96264` fixes the previously observed local M1 failure paths in a tracked, judgeable source tree: clean `/app` download source, strict app-bundle signing with sealed resources, visible launch surface, tracked-only extension packaging, and package literal scrub. Mounted local DMG strict codesign passes, but this is not public proof.
- The reverted `20260607T114534Z` slice added a local executor package smoke and caught a local ad-hoc signing pass, but the separate judge proved it did not fix production M1.
- The reverted `20260607T084004Z` slice built a local executor download page and ad-hoc signed zip, and it removed some owner/eval literals from changed package-path code. The separate judge proved this did not fix production M1.
- The reverted `20260607T075335Z` slice showed a local production-linked DMG could be rebuilt with sealed resources after ad-hoc signing, but the judge ruled it `FAKE/TAMPER` before public verification because the product diff was outside the judged executor commit and the rebuilt packaged archive contained owner/person-specific product literals.
- The reverted `20260607T064745Z` slice showed the local executor Swift app can open on Main, but the separate judge proved this does not change or prove production `anticipy.ai/app`.
- The reverted `20260607T035948Z` slice showed a local executor app can be packaged as a zip and served from the local Next app, but the separate judge proved this does not prove the production public front door.
- Production `https://www.anticipy.ai/app` belongs to Vercel project `anticipy`, not this repo's linked `anticipy-executor-working` project.
- Production `/download` and canonical `/dl/Anticipy_1.0.0_aarch64.dmg` still need a release-path fix, signature/resource fix, launch-surface fix, and clean judge verification. Builder header checks and local screenshots are not proof.

Not proven:
- M1 is not proven. The actual production public app must launch to a readable live Anticipy surface from a clean front-door path.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public download alone is not onboarding, self-connect, or stranger task completion.

Pending gates:
- No hard human gate blocks all work.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Current builds can be ad-hoc signed, but full zero-warning stranger install needs Developer ID and notarization. The production DMG app also has a resource-signature failure, which is a fixable packaging defect and not a reason to mark M1 done.
- Codex CLI usage for separate builder/judge sessions is currently exhausted. The CLI reported a reset on June 12, 2026 at 5:34 PM local time, with purchasing more credits as the other option. Spending money is a hard human gate and was not taken. Current-session local work can continue, but the separate judge cannot run until quota resets or the human chooses to spend money.
- OpenRouter credit is very low. Paid Gemini cross-checks hit HTTP 402 during M1 judges; the latest judge used a tiny Gemini-family prompt that agreed with `FAKE`. If all required different-family cross-checks become unavailable, record a human money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked paths.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/5 verified, 0 percent.
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
- Treating production-linked source commit `ccc96264` as M1 proof. It is pending build evidence until the canonical public front door and public DMG are updated and separately judged.
- Running `scripts/ship.sh` blindly. It rebuilds, uploads to R2, commits a manifest, and pushes `HEAD:main`. That may be the eventual ship path, but it must be reconciled with main-branch safety and judgeability before use.
- Making product changes in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` while the judged executor commit contains only logs. The judge will scan the external tree and treat uncommitted product deltas as a tamper risk. Product changes must live in a tracked, reviewable commit in the source tree being judged, or the loop must explicitly adapt to commit and scan the production-linked repo.
- Rebuilding packaged extension or app archives that contain owner/person-specific literals such as owner names or example third-party names in product code. Clean or isolate those literals before packaging.
- Treating the local executor Next page, local zip, local package smoke, or local Swift app launch as proof for production `anticipy.ai/app`.
- Treating the local executor download slice from `20260607T084004Z` or the local package smoke from `20260607T114534Z` as a production fix. The judge proved public M1 still fails.
- Blindly deploying this executor worktree to production `anticipy`, because production has a larger app and belongs to the older `Anticipy-DEV-FINAL` source tree.
- Treating authenticated-owner Chrome observations as clean stranger proof.
- Treating public headers, local app launch, local screenshots, or app activation by name as M1 proof without the separate judge.
- Treating the current 2.5 GB public DMG as a healthy normal verifier path. It completed, but it made a single M1 judge take tens of minutes.
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, empty-plan `goal_done`, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- Resolve the safe production deploy/judge path for production commit `ccc96264`, then run the separate M1 judge against the canonical public front door once Codex CLI quota allows it.
- Keep shrinking or deferring the 2.5 GB public artifact as a follow-up, because a normal M1 judge should complete in minutes.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
