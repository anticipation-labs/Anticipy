# STATE

Current milestone: M1 remains the active judged milestone because the public front door has not passed the separate clean-profile judge. While separate judge quota is blocked, unblocked M2/M3 perimeter work may continue as candidate work only. M2 now has unjudged typed Calendar routing, API-backed Google Calendar create, and API read-back UI candidates, and M3 has unjudged browser-action, browser-read, no-submit form-fill, native-bridge stale-loopback cleanup, Desktop extension refresh, packaged browser bridge status, honest Chrome setup gating, native bridge local self-test, and browser bridge diagnostic candidates, but none of these are proof.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed the planted-fake self-check, passed the computer-use self-test, scanned builder commit `76fc00d`, and found no tamper. It opened the clean public front door, downloaded the then-public 2.5 GB DMG, mounted it, and launched the public app. The public app failed M1 because `codesign --verify --strict` and `spctl --assess` failed with `code has no resources but signature indicates they must be present`, and launch produced an invisible app process with zero windows instead of a readable live Anticipy surface. The different-family Gemini cross-check agreed with `FAKE`. Proof: `logs/verdicts/20260607T114534Z.md`.

Latest builder lap: `20260608T070852Z` is `PENDING_JUDGE`, not proof. Production-linked repo `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` branch `rebuild/spine-clean` now has tracked manifest/site commit `dd9b3e4a97805145a884a4714c00a52f7f333282`, pointing the public release manifest at product commit `9184ce213d7d1b7676007fae670d6c0fc827b0ef`. The staged ship path uploaded the latest `178876640` byte DMG to a commit-addressed R2 key, committed the manifest, deployed the prebuilt public site without pushing git, and verified public state convergence plus full public DMG SHA. Public `https://www.anticipy.ai/api/app/state` now reports site commit `dd9b3e4`, release SHA `8c2090efa2365dc67e6dc8f99986ed37783142875c45700dc6e8f2ed173d0d49`, manifest release commit `9184ce213d7d1b7676007fae670d6c0fc827b0ef`, and `178876640` bytes. Checks also passed R2 HEAD, public `/app` HEAD, public `/dl/Anticipy_1.0.0_aarch64.dmg` HEAD, and headless public page inspection showing the download page plus macOS DMG link. The separate judge has not verified this public candidate.

Current public production candidate, pending judge:
- Public site commit: `dd9b3e4a97805145a884a4714c00a52f7f333282`.
- Public DMG source commit in manifest: `9184ce213d7d1b7676007fae670d6c0fc827b0ef`.
- Public DMG SHA-256: `8c2090efa2365dc67e6dc8f99986ed37783142875c45700dc6e8f2ed173d0d49`.
- Public DMG size: `178876640` bytes.
- Public R2 URL: `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/builds/9184ce213d7d1b7676007fae670d6c0fc827b0ef/Anticipy_1.0.0_aarch64.dmg`.
- `https://www.anticipy.ai/api/app/state` reports the expected site commit, release SHA, manifest release commit, and byte count.
- `https://www.anticipy.ai/app` returns 200 HTML.
- `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` returns `200`, `application/x-apple-diskimage`, and `Content-Length: 178876640`.
- `SHIP_DEPLOY=1 scripts/ship_candidate.sh` completed full public DMG SHA verification for this public candidate.

Current M2/M3 candidates included in the public candidate, pending judge:
- Product source commit `8d1898259ecb05f86b678d4e686e46744bb6e382` routes explicit typed Calendar instructions with full date/time into a pending `calendar_event` plan and Google Calendar template URL instead of generic browser search.
- Product source commit `f05cc8449c278b96b9a2cb1d18bdf7bfa25a0808` stops no-context browser action tasks from falling into search and wires explicit-site browser tasks into the bridge-backed dispatcher.
- Product source commit `af23bf28a3e26f5d4612c680aaa39fc2b92186f9` adds deterministic explicit-site action planning, fast planner-unavailable ask behavior, clearer typed-task ask display, and alternate-port packaged sidecar launch support.
- Product source commit `229cb45a170806308acc0a317bdd37028b15d360` completes simple read-only browser tasks from observed surface state without planner spend and shows the packaged UI result as `Done`.
- Product source commit `235dc1f39f79e109af14132fa24c25c673aeb25d` fills one simple standard form field on explicit loopback no-submit tasks with DOM-derived selector targeting and exact read-back.
- Product source commit `0c867f9690e08cb5ebfc3197620ed1f7f2c6d28c` lets the native host retry trigger listener binding and lets packaged Tauri stop only Anticipy-owned stale legacy loopback bridge processes before native messaging binds.
- Product source commit `049f4ad07250881f2034520b00fe578f6b95ebde` refreshes product-owned Desktop load-unpacked extension copies from the bundled v6 payload and aligns the wizard path with the Desktop folder Chrome is registered to load.
- Product source commit `47e92b6e10c6909dd7f65080fa3ed383c4c71020` surfaces browser bridge readiness in the packaged app through a read-only Tauri status command and a visible popover warning for disabled or miswired Chrome extension/native-host states.
- Product source commit `b57e3b1a13439471ebe479a48bdbc5c1a40d3810` makes browser bridge setup honest by rejecting stale legacy loopback status, detecting Chrome extension path mismatches, adding Copy path, and requiring a real bridge connection before wizard Step 2 advances.
- Product source commit `71829156f6db358adc1cc2448c3144dbed280498` adds a native-bridge-only local browser hands self-test, value read-back from extension type commands, value-preserving command proof, a ready-only popover self-test card, refreshed committed extension archives, and refreshed Desktop load-unpacked copies.
- Product source commit `5942dc0dff99647013e7a8573e59fdb7c8295318` adds visible browser bridge diagnostics to the packaged popover warning for extension staging, native host, Chrome registration/enabled/path-match state, and bridge state.
- Product source commit `cf8178e2c2454fe91a8b86788656d206d23eab5a` adds an API-backed Google Calendar create path for explicit typed, fully time-grounded Calendar tasks and packages the helper into the sidecar.
- Product source commit `9184ce213d7d1b7676007fae670d6c0fc827b0ef` requires Google Calendar API read-back before success, returns `VERIFY_FAILED` for created-but-unverified side effects without browser fallback, and surfaces read-back status in the typed-task UI.
- Checks across these candidates include Python compile, JS parse, Rust format/check, planner probes, non-destructive HTTP smokes, local loopback form smokes, isolated stale-bridge smoke, isolated extension-copy smoke, local native bridge self-test endpoint/page smoke, Browser localhost render, archive payload inspection, fake-network Calendar API insert and read-back probes, mocked Calendar server branch probes, headless Playwright and Computer Use renders, `bash scripts/build_dmg.sh`, packaged strict codesign, packaged sidecar smoke, filtered Chrome status checks, Computer Use packaged UI/screen inspection where available, and forbidden-literal scans.
- These are not M2 or M3 proof. The separate judge has not typed a task in the packaged app and verified a correct real artifact, browser action, or native browser bridge.

Gate status: no hard human gate blocks all work. Separate Codex CLI usage for independent builder/judge sessions is exhausted until the reported reset on June 12, 2026 at 5:34 PM local time unless money is spent. Spending money is a hard human gate and was not taken. Current-session local/product work can continue, but the separate judge cannot run until quota resets or the human chooses to spend money.

Pending cleanup/gates:
- Possible cleanup item: a native Apple Calendar smoke may have created `[Anticipy test] M2 typed smoke 20260607-continue` on June 12, 2026 from 15:00 to 16:00. Local read-back/delete was blocked by macOS privacy/TCC and AppleScript list timeouts. This is queued in `PENDING_FOR_OMAR.md`; do not delete or modify real existing Calendar data.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Current builds can be ad-hoc signed and strict codesign passes, but full zero-warning stranger install needs Developer ID and notarization.
- OpenRouter credit is very low. Paid Gemini cross-checks hit HTTP 402 during recent M1 judges, and the packaged model-driven browser action planner cannot currently get model steps. If required different-family cross-checks or planner calls are unavailable, record a human money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked deterministic paths.
- Owner Chrome currently has Anticipy extension id `npnpagopediecennpleihemoochikggb` registered at `/Users/omarebrahim/Desktop/Anticipy-Extension`, but disabled. The builder did not enable it through UI because browser-extension install/enable through Computer Use requires action-time confirmation. Continue unblocked product work and leave judge-visible proof to the separate judge or a user-confirmed enable path.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- M1 is not proven. The actual production public app must be downloaded and launched by the separate judge from a clean public front-door path.
- M2 is not proven. The separate judge has not typed a task in the packaged app and verified a real, correct, safe artifact.
- M3 is not proven. The separate judge has not verified a real browser action through the packaged app and bridge-backed hands.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public download alone is not onboarding, self-connect, or stranger task completion.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/5 verified, 0 percent. The public candidate `dd9b3e4a` plus release `8c2090ef...` is pending judge and does not change this number.
- M2 packaged typed-input reality judge pass rate: 0/0 verified; not run.
- M3 packaged/browser-hands reality judge pass rate: 0/0 verified; not run.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: active. Builder-owned tests remain green while M1 reality pass rate is 0 percent. Do not advance M1, M2, or M3 from local app launch, local packaging, public headers, public SHA checks, owner Chrome observations, or screenshots without the separate judge seeing the clean production front door and real app artifact.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Treating production-linked source commits `229cb45a`, `af23bf28`, `f05cc844`, `8d189825`, `9a2aa885`, `ff5c470f`, `f370f7c9`, `bdc0e76e`, `ca16ffe1`, `dd9b3e4a`, `9184ce21`, or their ancestors as M1, M2, or M3 proof. They are pending until the separate judge verifies the canonical public front door, public DMG, app launch, packaged typed task, and real action artifact.
- Treating production-linked source commits `235dc1f3`, `0c867f96`, `049f4ad0`, `47e92b6e`, `b57e3b1a`, `71829156`, `5942dc0d`, `cf8178e2`, or `9184ce21` as M2 or M3 proof. They are pending until the separate judge verifies the packaged app, typed task, API artifact, or browser hands on a safe, reversible task.
- Treating the packaged browser bridge diagnostic banner or Computer Use read-only app inspection as M3 proof. The banner is recovery UI only until a separate judge verifies packaged native bridge action.
- Treating the local self-test endpoint, extension value read-back, extension zip hashes, refreshed Desktop extension folders, archive payload inspection, fake-network Calendar insert probe, mocked server branch probe, or Browser localhost popover render as proof. They are candidate plumbing only until a separate judge verifies a real artifact or browser action.
- Assuming Chrome AppleScript JavaScript is enabled. It was off in the normal owner Chrome on this Mac; controlled CDP was used only for safe loopback smoke. For real product proof, prefer the installed extension/native bridge path or another explicit, judge-visible browser-control path.
- Treating the current stale-loopback cleanup as proof that the native Chrome extension bridge is connected. The latest smoke proved safe cleanup and a free trigger port only. It did not prove extension native-host selector typing.
- Treating refreshed Desktop extension folders as proof that Chrome native messaging is connected. The folders are v6 with native messaging, but owner Chrome currently has the extension disabled and `127.0.0.1:7777` does not answer.
- Dumping raw Chrome profile preference files. Use filtered JSON parsing for the Anticipy extension id only.
- Using native local Apple Calendar as an autonomous proof path when read-back/delete is blocked by macOS privacy or AppleScript hangs. Do not create real Calendar artifacts unless cleanup and read-back are reliable.
- Running old `scripts/ship.sh` blindly. It rebuilds, uploads to the old canonical R2 key, commits a manifest, and pushes `HEAD:main`. Use the no-push `scripts/ship_candidate.sh` path for judgeable public candidates.
- Comparing Vercel live commit seven characters to Git's default eight-character short SHA. Use `git rev-parse --short=7 HEAD`.
- Letting stale untracked `public/Anticipy.dmg` enter Vercel output. It exceeds Vercel's 100 MB file limit and is not the canonical R2 download.
- Using path-sorted DMG selection after a Tauri build. That selected stale 2.5 GB artifacts. Prefer the target-specific fresh DMG path.
- Letting extension zip archive metadata churn dirty the tree every package run. Use the deterministic packager from `ca16ffe1`, and do not commit regenerated zips unless extension source changed or the package content intentionally changed.
- Making product changes in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` while the judged executor commit contains only logs. The judge will scan the external tree and treat uncommitted product deltas as a tamper risk. Product changes must live in a tracked, reviewable commit in the source tree being judged, or the loop must explicitly adapt to commit and scan the production-linked repo.
- Rebuilding packaged extension or app archives that contain owner/person-specific literals or eval-control literals in product code. Clean or isolate those literals before packaging.
- Treating the local executor Next page, local zip, local package smoke, local Swift app launch, owner Chrome, public headers, public SHA, or mocked Playwright probes as proof for production `anticipy.ai/app`.
- Treating authenticated-owner Chrome observations as clean stranger proof.
- Treating the old 2.5 GB public DMG as a healthy normal verifier path. It made a single M1 judge take tens of minutes. The public `9a2aa885` candidate is about 171 MB, but still needs separate judge proof.
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, screenshot-only browser proof, guard-only proof, abstention, ask-only behavior, empty-plan `goal_done`, or any support-only proof as completed real-world actions.
- Do not let the planner type a whole task into a browser search bar as a substitute for decomposition. Explicit lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not let browser planner model failures loop to the dispatcher step cap. Low-credit or missing-model paths must fail fast, ask clearly, and stay visible in logs.
- Do not use capture timestamps as event times unless the user explicitly asked for now. Supply real observed clock and transcript timing context instead.
- Do not auto-prompt macOS microphone permission on first launch. It is a user-action permission, not part of the M1 stranger first-view surface.

Next:
- When separate judge quota is available, run the separate M1 judge against public production site commit `dd9b3e4a97805145a884a4714c00a52f7f333282` and release SHA `8c2090efa2365dc67e6dc8f99986ed37783142875c45700dc6e8f2ed173d0d49`.
- If M1 passes, run an M2/M3 judge that types a safe, reversible, fully time-grounded task in the packaged app and verifies the real artifact or browser action.
- While judge quota is blocked, keep improving unblocked production-source perimeter slices without claiming proof. The next useful slices are continuing safe browser-hands readiness work or preparing the pending M1/M2 judge path for when separate judge quota returns.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, public headers, owner Chrome checks, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
