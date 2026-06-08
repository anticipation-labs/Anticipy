# STATE

Current milestone: M1 remains the active judged milestone because the public front door has not passed the separate clean-profile judge. While separate judge quota is blocked, unblocked M2, M3, and M5 perimeter work may continue as candidate work only. The latest public candidate is an M3 explicit Google search phrasing candidate, publicly deployed but unjudged.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed the planted-fake self-check, computer-use self-test, diff scan, and different-family cross-check. It opened the clean public front door, downloaded the then-public 2.5 GB DMG, mounted it, and launched the public app. The public app failed because strict codesign and `spctl --assess` failed with a resource-signature error, and launch produced an invisible app process with zero windows. Proof: `logs/verdicts/20260607T114534Z.md`.

Latest builder lap: `20260608T145524Z` is `PENDING_JUDGE`, not proof. Production-linked repo `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` branch `rebuild/spine-clean` now has tracked engine source commit `ed5c45ccec915ff076bab249d8fe467a57e42ebf` and manifest/site commit `9153bbee69c032ae38001428a2348dd7fce30442`.

Latest product change:
- The server-side direct browser plan recognizes explicit Google lookup phrasing such as `open google and search for hiking socks`.
- The route returns `open_search_tab` with only the extracted query, preventing the whole instruction from being typed into a search bar for this explicit Google search pattern.
- Non-Google and non-search action text stays out of this direct search path.
- The package manifest now points at DMG source commit `ed5c45ccec915ff076bab249d8fe467a57e42ebf`.

Current public production candidate, pending judge:
- Public site commit: `9153bbee69c032ae38001428a2348dd7fce30442`.
- Public DMG source commit in manifest: `ed5c45ccec915ff076bab249d8fe467a57e42ebf`.
- Public DMG SHA-256: `d4c442db4691b8ce717977fa9b39b5eb359a76852db27cd1a284590dd90944da`.
- Public DMG size: `178891486` bytes.
- Public R2 URL: `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/builds/ed5c45ccec915ff076bab249d8fe467a57e42ebf/Anticipy_1.0.0_aarch64.dmg`.
- `https://www.anticipy.ai/api/app/state` reports site commit `9153bbe`, release SHA `d4c442db4691b8ce717977fa9b39b5eb359a76852db27cd1a284590dd90944da`, manifest release commit `ed5c45ccec915ff076bab249d8fe467a57e42ebf`, and `178891486` bytes.
- `https://www.anticipy.ai/app` returns 200 HTML.
- `https://www.anticipy.ai/install.sh` returns 200 shell script.
- `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` returns 200 disk image with content length `178891486`.
- The public `/app` rendered release line is `Build ed5c45c | 178.9 MB | Updated 2026-06-08 | SHA-256 d4c442db4691...590dd90944da`.

Latest checks, candidate evidence only:
- Mandatory compaction-proof reads were re-run for `AGENTS.md`, `autopilot/02_LAWS.md`, `autopilot/09_REPO_FACTS.md`, `logs/STATE.md`, `autopilot/00_START_HERE.md`, `CODEX_BRIEF.md`, `logs/last_lap.md`, and `autopilot/07_MILESTONES.md`.
- `python3 -m py_compile engine/app/product/server.py` passed.
- Direct server probes mapped 3 explicit Google lookup variants to `open_search_tab` with query-only targets.
- Negative probes for Google Calendar, non-Google site search, and dentist booking text did not become `open_search_tab`.
- `git diff --check` passed.
- Forbidden path scan found no edits under `tests/`, `judge/`, `realdays/holdout/`, or `scripts/realday.sh`.
- Owner/eval literal scan found no matches in the touched product diff.
- `scripts/ship_candidate.sh` built and uploaded the package DMG with SHA `d4c442db4691b8ce717977fa9b39b5eb359a76852db27cd1a284590dd90944da` and size `178891486` bytes.
- Local DMG SHA matched the manifest, and R2 HEAD returned `200` with content length `178891486`.
- `SHIP_DEPLOY=1 scripts/ship_candidate.sh` deployed the candidate and verified the full public DMG SHA.
- Public `/api/app/state`, `/app`, `/install.sh`, and `/dl/Anticipy_1.0.0_aarch64.dmg` checks passed.
- Fresh Playwright browser context on `https://www.anticipy.ai/app` found the current release line, canonical DMG link, install command, and zero page console warnings/errors.
- Screenshot evidence is local at `/tmp/anticipy-public-app-20260608T145524Z.png`.
- Product repo has no tracked dirty files after deploy; only pre-existing untracked artifacts remain.
- No installer was executed, and no real external artifact, UI click, extension enablement, browser action, SMS, email, Calendar action, source scrape, phone call, audio upload, account action, third-party action, or form submission was performed by the builder.

Current M2/M3/M5 candidates in the production-linked source, pending judge:
- M2 typed task and Calendar candidates include explicit typed Calendar routing, API-backed Google Calendar create, API read-back before success, packaged typed-task result UI, structured browser proof rows, ask-user choice buttons, persistent listening start/stop control, typed client clock grounding, and account form submit behavior.
- M3 browser-hands candidates include explicit-site routing, read-only browser answers, no-submit browser form fill, multi-field no-submit form fill, broader safe no-submit fill wording for input/box/textarea/text area plus set/put verbs, search-bar no-submit fill wording, broader search-target type repair, direct explicit Google search phrasing, visible proof rows, ask-user retry/cancel/review choices, native bridge stale-loopback cleanup, Desktop extension refresh, packaged browser bridge status and diagnostics, native bridge self-test, native action-search guard, broader action-search boundary, generic bridge primitive dispatch for click/type/key/read/extract/DOM snapshot, search-box type repair, broader site-search phrasing repair, early SMS pre-confirm for internal action-engine callers, direct browser primitive bridge preference when CDP is unavailable, and browser listen fastpath honesty that marks background open/search as `started` and `ATTEMPTED` until completion proof exists.
- M5 onboarding candidates include profile/SMS persistence honesty, cold-start readiness honesty, cold-start status polling honesty, onboarding SMS endpoint, browser readiness requiring a real local native-bridge self-test before Step 2 advances, clean account-path form plus no pre-session localhost probe, call-onboarding form plus no submit before explicit engine readiness, chat-onboarding explicit start with no model or loopback work on page load, and audio-onboarding explicit engine readiness before file selection or upload.
- These are not proof. The separate judge has not typed a task in the packaged app and verified a real artifact, browser action, native bridge action, record-control behavior, relative-date clock behavior, or onboarding mesh.

Gate status:
- No hard human gate blocks all work.
- Separate Codex CLI usage for independent builder/judge sessions is exhausted until the reported reset on June 12, 2026 at 5:34 PM local time unless money is spent. Spending money is a hard human gate and was not taken.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities. Current builds can be ad-hoc signed and strict codesign passes, but full zero-warning stranger install needs Developer ID and notarization.
- OpenRouter credit is very low. Paid Gemini cross-checks hit HTTP 402 during recent M1 judges, and packaged model-driven browser action planning can fail fast to ask. If required different-family cross-checks or planner calls are unavailable, record a money/key gate in `PENDING_FOR_OMAR.md` and keep working on unblocked deterministic paths.
- Owner Chrome has Anticipy extension id `npnpagopediecennpleihemoochikggb` registered at `/Users/omarebrahim/Desktop/Anticipy-Extension`, but disabled. The builder did not enable it through UI because extension enablement is a user-action confirmation. Leave judge-visible proof to the separate judge or an explicit user-confirmed enable path.
- Possible cleanup item: a native Apple Calendar smoke may have created `[Anticipy test] M2 typed smoke 20260607-continue` on June 12, 2026 from 15:00 to 16:00. Local read-back/delete was blocked by macOS privacy/TCC and AppleScript list timeouts. This is queued in `PENDING_FOR_OMAR.md`; do not delete or modify real existing Calendar data.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- M1 is not proven. The current public production app must be downloaded, installed, and launched by the separate judge from the clean public front door.
- M2 is not proven. The separate judge has not typed a task in the packaged app, verified a real correct artifact, verified relative-date clock grounding, or verified the real record/listen control.
- M3 is not proven. The separate judge has not verified a real browser action through the packaged app and bridge-backed hands.
- M5 is not proven. The separate judge has not completed onboarding on a fresh account and verified a working personal mesh.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public account form, onboarding forms, installer safety, public renders, and preflight checks are not onboarding, self-connect, or stranger task completion.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/5 verified, 0 percent. The public candidate `9153bbe` plus release `d4c442db...` is pending judge and does not change this number.
- M2 packaged typed-input/listen-control/clock-grounding reality judge pass rate: 0/0 verified; not run.
- M3 packaged/browser-hands reality judge pass rate: 0/0 verified; not run.
- M5 packaged/self-onboarding reality judge pass rate: 0/0 verified; not run.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: active. Builder-owned tests remain green while M1 reality pass rate is 0 percent. Do not advance M1, M2, M3, or M5 from local app launch, local packaging, public headers/SHA, browser automation observations, owner Chrome observations, local process/window enumeration, screenshots, release metadata, installer static checks, installer preflight checks, account form checks, onboarding form checks, or public app renders without the separate judge seeing the clean production front door and real app artifact.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Treating any production-linked source, manifest commit, public build commit, public headers, public SHA, public release metadata, public install script, successful site deploy, public account/onboarding form check, public audio-readiness check, public installer cleanup, public installer safe replacement, delayed installer service stops, installer preflight checks, browser-rendered public page, local packaging, local launch, owner Chrome, screenshot, or process/window enumeration as M1, M2, M3, or M5 proof before the separate judge verifies the real public front door, public DMG, app launch, packaged typed task, browser/action artifact, listen-control behavior, relative-date clock behavior, or fresh-account onboarding path.
- Letting action-shaped prose become browser search. Explicit lookup may search; action tasks must route to API hands, browser hands with explicit site context, or a visible ask/needs-human.
- Letting browser planner model failures loop to the dispatcher step cap. Low-credit or missing-model paths must fail fast, ask clearly, and stay visible in logs.
- Running old `scripts/ship.sh` blindly. It rebuilds, uploads to the old canonical R2 key, commits a manifest, and pushes `HEAD:main`. Use `scripts/ship_candidate.sh` and never push.
- Treating a nonzero `scripts/ship_candidate.sh` final convergence check as success without manual public state, header, and full SHA verification.
- Letting stale untracked `public/Anticipy.dmg` enter Vercel output. It exceeds Vercel's 100 MB file limit and is not the canonical R2 download.
- Letting extension zip archive metadata churn dirty the tree every package run. Restore regenerated zips unless extension source changed or package content intentionally changed.
- Making product changes in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` without a tracked, judgeable product commit in that source tree.
- Rebuilding packaged extension or app archives that contain owner/person-specific literals or eval-control literals in product code.
- Using native local Apple Calendar as autonomous proof when read-back/delete is blocked by macOS privacy or AppleScript hangs.
- Dumping raw Chrome profile preference files. Use filtered JSON parsing for the Anticipy extension id only.
- Assuming Chrome AppleScript JavaScript is enabled.
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not auto-prompt macOS microphone permission on first launch. It is a user-action permission, not part of the M1 stranger first-view surface.

Next:
- When separate judge quota is available, run the separate M1 judge against public production site commit `9153bbee69c032ae38001428a2348dd7fce30442` and release SHA `d4c442db4691b8ce717977fa9b39b5eb359a76852db27cd1a284590dd90944da`.
- If M1 passes, run an M2/M3/M5 judge that types a safe, reversible, fully time-grounded task in the packaged app, verifies the real artifact or browser action, verifies packaged listen control behavior, and verifies onboarding mesh on a fresh account.
- While judge quota is blocked, keep improving unblocked perimeter work without claiming proof.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, public headers, release metadata, public account/onboarding checks, public installer checks, owner/browser checks, process/window enumeration, screenshots, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
