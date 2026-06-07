# STATE

Current milestone: M1, real front door. M1 means a clean profile can download a Mac app from the public front door at `anticipy.ai/app`, launch it, and see the live Anticipy surface. M0 clean floor is proven once, but the product is not done until a stranger can download, onboard, connect their own apps, and get a real task done.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed the planted-fake self-check, passed the computer-use self-test, scanned builder commit `76fc00d`, and found no tamper. It opened the clean public front door, downloaded the then-public 2.5 GB DMG, mounted it, and launched the public app. The public app failed M1 because `codesign --verify --strict` and `spctl --assess` failed with `code has no resources but signature indicates they must be present`, and launch produced an invisible app process with zero windows instead of a readable live Anticipy surface. The different-family Gemini cross-check agreed with `FAKE`. Proof: `logs/verdicts/20260607T114534Z.md`.

Current pending unjudged production candidate: `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` branch `rebuild/spine-clean`, commit `bdc0e76e`. This candidate is tracked, deployed to public `https://www.anticipy.ai`, and not pushed to git origin. It is not M1 proof until the separate judge verifies the clean public front door and public app launch.

What the public candidate contains:
- M1 fixes from `ccc96264`: public `/app` source starts on the download surface, Tauri signs and verifies the app bundle root before DMG creation, packaged app launch shows a readable Anticipy popover, package-path owner/eval literals were scrubbed, bridge screenshot paths use the current home directory, and extension packaging copies only git-tracked files.
- M1 size fix from `20de47b5`: default front-door DMG skips the 2.3 GB Parakeet ASR model unless `ANTICIPY_BUNDLE_ASR_MODEL=1`, leaving audio weights for later audio milestones.
- M2 perimeter slice from `ca16ffe1`: the packaged Tauri popover has a persistent typed-task composer. Submit calls `/api/listen/inject` first and then `/api/act` when work remains; already-acted browser fast-path injects render done; confirm-required actions render Approve and Reject controls backed by `/api/act/confirm/{task_id}`.
- Packaging hardening from `ca16ffe1`: `scripts/build_dmg.sh` prefers the fresh target-specific Tauri DMG path and only falls back to newest mtime, so the root `target/release` copy no longer path-sorts into stale 2.5 GB artifacts. `scripts/v7/package_extension_v6.sh` writes deterministic zips with fixed timestamps and sorted file order.
- Public ship path from `4c4fbe32` through `bdc0e76e`: `scripts/ship_candidate.sh` stages a commit-addressed R2 object, writes manifest URL/bytes/SHA, pulls Vercel production settings, builds, deploys prebuilt production output without git push, retries transient Vercel upload failures, excludes stale local DMGs from Vercel output, and verifies public state plus public DMG SHA.

Public candidate facts, not judge proof:
- Public build commit: `bdc0e76ee8a1252680565bd232f6f373f90734f8`.
- Public release manifest commit: `4c4fbe326b4cc39dbe2320fa478fb54c2583b92b`.
- Public DMG SHA-256: `e527a3d8ba8d52512f35d48bc55bad8a51cbf33f8ed875a9446ccada6f861aac`.
- Public DMG size: `178811741` bytes.
- Public R2 URL: `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/builds/4c4fbe326b4cc39dbe2320fa478fb54c2583b92b/Anticipy_1.0.0_aarch64.dmg`.
- `https://www.anticipy.ai/api/app/state` reports the expected build, release SHA, manifest commit, and bytes.
- `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` HEAD reports `200`, `application/x-apple-diskimage`, and `Content-Length: 178811741`.
- `SHIP_DEPLOY=1 scripts/ship_candidate.sh` completed full public DMG SHA verification.
- Real Chrome owner-profile sanity check loaded `anticipy.ai/app` and showed the Anticipy live surface. This is not clean stranger proof.

Build-side checks for the current production stack, not proof:
- `npm run build` passed before and after the manifest update.
- `bash -n scripts/ship_candidate.sh` passed after every script change.
- Candidate DMG built and uploaded from commit `4c4fbe32`.
- R2 candidate HEAD returned correct disk-image content type and byte length.
- Vercel prebuilt deploy succeeded after removing stale `public/Anticipy.dmg` from the build surface.
- Earlier `ca16ffe1` checks still apply: inline popover script parse, `git diff --check`, unchanged popover e2e 3/3, one-off Playwright typed-composer probe, deterministic extension zip stability, `bash scripts/build_dmg.sh`, mounted-DMG `codesign --verify --strict`, zero Parakeet resources, and packaged launch screenshot with composer visible.
- `spctl --assess` still rejects the app because it is ad-hoc signed and this Mac has no Developer ID identity.

Gate status: no hard human gate blocks all work. The failed builder commit `76fc00d` was reverted by `969218d` and must not be merged to `main`. The failed lap `20260607T075335Z` remains reverted by `d80f0ce`, with its failed production-linked diff preserved as `stash@{0}: failed lap 20260607T075335Z m1 package slice` in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`. The current production commit `bdc0e76e` is public and judgeable but must not be represented as M1 or M2 done until the separate judge verifies reality.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- M1 is not proven. The actual production public app must be downloaded and launched by the separate judge from a clean public front-door path.
- M2 is not proven. The separate judge has not typed a task in the packaged app and verified a real, correct, safe artifact.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public download alone is not onboarding, self-connect, or stranger task completion.

Pending gates:
- No hard human gate blocks all work.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Current builds can be ad-hoc signed and strict codesign passes, but full zero-warning stranger install needs Developer ID and notarization.
- Codex CLI usage for separate builder/judge sessions is currently exhausted. The CLI reported a reset on June 12, 2026 at 5:34 PM local time, with purchasing more credits as the other option. Spending money is a hard human gate and was not taken. Current-session local work can continue, but the separate judge cannot run until quota resets or the human chooses to spend money.
- OpenRouter credit is very low. Paid Gemini cross-checks hit HTTP 402 during M1 judges; the latest judge used a tiny Gemini-family prompt that agreed with `FAKE`. If all required different-family cross-checks become unavailable, record a human money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked paths.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/5 verified, 0 percent. The public candidate `bdc0e76e` is pending judge and does not change this number.
- M2 packaged typed-input reality judge pass rate: 0/0 verified; not run.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: active. Builder-owned tests remain green while M1 reality pass rate is 0 percent. Do not advance M1 or M2 from local app launch, local packaging, public headers, public SHA checks, owner Chrome observations, or screenshots without the separate judge seeing the clean production front door and real app artifact.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Treating production-linked source commit `bdc0e76e`, `ca16ffe1`, or their ancestors as M1 or M2 proof. They are pending until the separate judge verifies the canonical public front door, public DMG, app launch, and packaged typed task.
- Running old `scripts/ship.sh` blindly. It rebuilds, uploads to the old canonical R2 key, commits a manifest, and pushes `HEAD:main`. Use the no-push `scripts/ship_candidate.sh` path for judgeable public candidates.
- Comparing Vercel live commit seven characters to Git's default eight-character short SHA. Use `git rev-parse --short=7 HEAD`.
- Letting stale untracked `public/Anticipy.dmg` enter Vercel output. It exceeds Vercel's 100 MB file limit and is not the canonical R2 download.
- Using path-sorted DMG selection after a Tauri build. That selected stale `desktop/target/release/...` 2.5 GB artifacts. Prefer the target-specific fresh DMG path.
- Letting extension zip archive metadata churn dirty the tree every package run. Use the deterministic packager from `ca16ffe1`.
- Making product changes in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` while the judged executor commit contains only logs. The judge will scan the external tree and treat uncommitted product deltas as a tamper risk. Product changes must live in a tracked, reviewable commit in the source tree being judged, or the loop must explicitly adapt to commit and scan the production-linked repo.
- Rebuilding packaged extension or app archives that contain owner/person-specific literals such as owner names or example third-party names in product code. Clean or isolate those literals before packaging.
- Treating the local executor Next page, local zip, local package smoke, local Swift app launch, owner Chrome, public headers, public SHA, or mocked Playwright probes as proof for production `anticipy.ai/app`.
- Treating authenticated-owner Chrome observations as clean stranger proof.
- Treating the old 2.5 GB public DMG as a healthy normal verifier path. It made a single M1 judge take tens of minutes. The public `bdc0e76e` candidate is about 171 MB, but still needs separate judge proof.
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, empty-plan `goal_done`, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.

Next:
- Run the separate M1 judge against public production build `bdc0e76e` when Codex CLI quota allows it.
- If M1 passes, run an M2 judge that types a safe, reversible, fully time-grounded task in the packaged app and verifies the real artifact.
- Keep the public artifact small enough that a normal M1 judge completes in minutes.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, public headers, owner Chrome checks, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
