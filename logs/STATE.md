# STATE

Current milestone: M1 remains the active judged milestone because the public front door has not passed the separate clean-profile judge. While separate judge quota is blocked, unblocked M2/M3 perimeter work may continue as candidate work only. M2 has an unjudged typed Calendar routing candidate, and M3 now has unjudged browser-action/read candidates, but none of these are proof.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed the planted-fake self-check, passed the computer-use self-test, scanned builder commit `76fc00d`, and found no tamper. It opened the clean public front door, downloaded the then-public 2.5 GB DMG, mounted it, and launched the public app. The public app failed M1 because `codesign --verify --strict` and `spctl --assess` failed with `code has no resources but signature indicates they must be present`, and launch produced an invisible app process with zero windows instead of a readable live Anticipy surface. The different-family Gemini cross-check agreed with `FAKE`. Proof: `logs/verdicts/20260607T114534Z.md`.

Latest builder lap: `20260608T033645Z` is `PENDING_JUDGE`, not proof. Production-linked repo `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` branch `rebuild/spine-clean` now has tracked product commit `229cb45a170806308acc0a317bdd37028b15d360`. It answers simple read-only browser tasks from concrete surface state without planner spend when the opened page already exposes the requested title, heading, URL, or short page text. Answered read-only `NOTIFY` results complete as `SUCCESS`; side-effect tasks and checkbox actions remain outside that completion path. The packaged task-box UI now renders answered browser reads as `Done`.

Current public production candidate, pending judge:
- Public site commit: `9a2aa8858ad3b2a6186a983b2160a081c8089421`.
- Public DMG source commit in manifest: `ff5c470f65c42ad24f0f55be68d6acf702d525d5`.
- Public DMG SHA-256: `0638e321c791039926cb66369462a5f068b00164f4ae5b81f7b51115c4ee10ad`.
- Public DMG size: `178815398` bytes.
- Public R2 URL: `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/builds/ff5c470f65c42ad24f0f55be68d6acf702d525d5/Anticipy_1.0.0_aarch64.dmg`.
- `https://www.anticipy.ai/api/app/state` reports the expected site commit, release SHA, manifest release commit, and byte count.
- `https://www.anticipy.ai/app` returns 200 HTML.
- `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` returns `200`, `application/x-apple-diskimage`, and `Content-Length: 178815398`.
- `SHIP_DEPLOY=1 scripts/ship_candidate.sh` completed full public DMG SHA verification for this public candidate.

Current unshipped M2/M3 candidates, pending judge and deploy decision:
- Product source commit `8d1898259ecb05f86b678d4e686e46744bb6e382` routes explicit typed Calendar instructions with full date/time into a pending `calendar_event` plan and Google Calendar template URL instead of generic browser search.
- Product source commit `f05cc8449c278b96b9a2cb1d18bdf7bfa25a0808` stops no-context browser action tasks from falling into search and wires explicit-site browser tasks into the bridge-backed dispatcher.
- Product source commit `af23bf28a3e26f5d4612c680aaa39fc2b92186f9` adds deterministic explicit-site action planning, fast planner-unavailable ask behavior, clearer typed-task ask display, and alternate-port packaged sidecar launch support.
- Product source commit `229cb45a170806308acc0a317bdd37028b15d360` completes simple read-only browser tasks from observed surface state without planner spend and shows the packaged UI result as `Done`.
- Checks across these candidates include Python compile, JS parse, Rust format/check, planner probes, non-destructive HTTP smokes, `bash scripts/build_dmg.sh`, packaged strict codesign, packaged sidecar smoke, Computer Use packaged UI inspection, and forbidden-literal scans on regenerated extension zips.
- These are not M2 or M3 proof. The separate judge has not typed a task in the packaged app and verified a correct real artifact or browser action.

Gate status: no hard human gate blocks all work. Separate Codex CLI usage for independent builder/judge sessions is exhausted until the reported reset on June 12, 2026 at 5:34 PM local time unless money is spent. Spending money is a hard human gate and was not taken. Current-session local/product work can continue, but the separate judge cannot run until quota resets or the human chooses to spend money.

Pending cleanup/gates:
- Possible cleanup item: a native Apple Calendar smoke may have created `[Anticipy test] M2 typed smoke 20260607-continue` on June 12, 2026 from 15:00 to 16:00. Local read-back/delete was blocked by macOS privacy/TCC and AppleScript list timeouts. This is queued in `PENDING_FOR_OMAR.md`; do not delete or modify real existing Calendar data.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Current builds can be ad-hoc signed and strict codesign passes, but full zero-warning stranger install needs Developer ID and notarization.
- OpenRouter credit is very low. Paid Gemini cross-checks hit HTTP 402 during recent M1 judges, and the packaged model-driven browser action planner cannot currently get model steps. If required different-family cross-checks or planner calls are unavailable, record a human money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked deterministic paths.
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
- M1 reality judge pass rate: 0/5 verified, 0 percent. The public candidate `9a2aa885` plus release `0638e321...` is pending judge and does not change this number.
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
- Treating production-linked source commits `229cb45a`, `af23bf28`, `f05cc844`, `8d189825`, `9a2aa885`, `ff5c470f`, `f370f7c9`, `bdc0e76e`, `ca16ffe1`, or their ancestors as M1, M2, or M3 proof. They are pending until the separate judge verifies the canonical public front door, public DMG, app launch, packaged typed task, and real action artifact.
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
- When separate judge quota is available, run the separate M1 judge against public production site commit `9a2aa8858ad3b2a6186a983b2160a081c8089421` and release SHA `0638e321c791039926cb66369462a5f068b00164f4ae5b81f7b51115c4ee10ad`.
- If M1 passes, run an M2/M3 judge that types a safe, reversible, fully time-grounded task in the packaged app and verifies the real artifact or browser action.
- While judge quota is blocked, keep improving unblocked production-source perimeter slices without claiming proof. The next useful slice is deterministic low-risk M3 browser form-field handling that can fill simple fields without submit when concrete surface marks are sufficient, while keeping all irreversible actions behind confirmation.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, public headers, owner Chrome checks, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
