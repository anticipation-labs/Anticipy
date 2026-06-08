# STATE

Current milestone: M1 remains the active judged milestone because the public front door has not passed the separate clean-profile judge. While separate judge quota is blocked, unblocked M2, M3, and M5 perimeter work may continue as candidate work only. The latest candidate is M1/M3 browser action-search boundary hardening, publicly deployed but unjudged.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed the planted-fake self-check, computer-use self-test, diff scan, and different-family cross-check. It opened the clean public front door, downloaded the then-public 2.5 GB DMG, mounted it, and launched the public app. The public app failed because strict codesign and `spctl --assess` failed with a resource-signature error, and launch produced an invisible app process with zero windows. Proof: `logs/verdicts/20260607T114534Z.md`.

Latest builder lap: `20260608T084430Z` is `PENDING_JUDGE`, not proof. Production-linked repo `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` branch `rebuild/spine-clean` now has tracked product commit `bb4319ab8e2d7d16725f04137e3cb8b88ea18b1e` and tracked manifest/site commit `549322cec573c8667e908c84a16c2736540d9e81`.

Latest product change:
- Broadened the browser action-search boundary in `engine/app/product/surface_runtime.py` and `engine/app/product/server.py`.
- Action-shaped typed tasks using message, text, call, invite, RSVP, register, unsubscribe, apply, purchase, checkout, appointment, reservation, delete, remove, and related verbs are now side-effect tasks, not generic lookup/search.
- `SurfaceRuntime.run_browser_task` refuses action-shaped `open_search_tab` before bridge availability or browser navigation.
- The universal browser dispatcher uses the same side-effect helper when no explicit site/app context exists, returning `needs_browser_context` instead of search.
- Explicit-site browser tasks with the new verbs become deterministic `browser_action` plans.

Current public production candidate, pending judge:
- Public site commit: `549322cec573c8667e908c84a16c2736540d9e81`.
- Public DMG source commit in manifest: `bb4319ab8e2d7d16725f04137e3cb8b88ea18b1e`.
- Public DMG SHA-256: `c0e8ca6778ce969fc32f02e7773ddb2026992c5162344132535f79182041f172`.
- Public DMG size: `178880091` bytes.
- Public R2 URL: `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/builds/bb4319ab8e2d7d16725f04137e3cb8b88ea18b1e/Anticipy_1.0.0_aarch64.dmg`.
- `https://www.anticipy.ai/api/app/state` reports site commit `549322c`, release SHA `c0e8ca6778ce969fc32f02e7773ddb2026992c5162344132535f79182041f172`, manifest release commit `bb4319ab8e2d7d16725f04137e3cb8b88ea18b1e`, and `178880091` bytes.
- `https://www.anticipy.ai/app` returns 200 HTML.
- `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` returns 200, `application/x-apple-diskimage`, and `Content-Length: 178880091`.
- Full public DMG SHA verification matched `c0e8ca6778ce969fc32f02e7773ddb2026992c5162344132535f79182041f172`.

Latest checks, candidate evidence only:
- Python compile passed for touched product files.
- Direct no-network routing probes passed for `SurfaceRuntime`, server helper functions, `_try_universal_browser_action`, and a patched `/api/act` path returning `needs_browser_context` without a search fallback.
- `git diff --check` passed and the touched diff had no forbidden owner/eval literals.
- Focused pytest could not run because the product venv lacks `pytest`.
- `bash scripts/build_dmg.sh` passed.
- Strict codesign passed.
- Embedded app commit verification passed.
- `hdiutil imageinfo` reported a valid compressed UDZO image.
- R2 HEAD passed for the commit-addressed DMG.
- `SHIP_DEPLOY=1 scripts/ship_candidate.sh` deployed without pushing git but exited nonzero after a final convergence check. Manual public checks showed correct convergence.
- Browser automation loaded the public front door, and a headless render found title `Anticipy App | Anticipy`, H1 `Bring Anticipy onto your Mac.`, and the canonical DMG link.
- No real external artifact, UI click, extension enablement, browser action, SMS, email, Calendar action, source scrape, or account action was performed by the builder.

Current M2/M3/M5 candidates in the production-linked source, pending judge:
- M2 typed task and Calendar candidates include explicit typed Calendar routing, API-backed Google Calendar create, and API read-back before success.
- M3 browser-hands candidates include explicit-site routing, read-only browser answers, no-submit form fill, native bridge stale-loopback cleanup, Desktop extension refresh, packaged browser bridge status and diagnostics, native bridge self-test, native action-search guard, and the latest broader action-search boundary.
- M5 onboarding candidates include profile/SMS persistence honesty, cold-start readiness honesty, cold-start status polling honesty, and the onboarding SMS endpoint.
- These are not proof. The separate judge has not typed a task in the packaged app and verified a real artifact, browser action, native bridge action, or onboarding mesh.

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
- M1 is not proven. The current public production app must be downloaded and launched by the separate judge from the clean public front door.
- M2 is not proven. The separate judge has not typed a task in the packaged app and verified a real, correct, safe artifact.
- M3 is not proven. The separate judge has not verified a real browser action through the packaged app and bridge-backed hands.
- M5 is not proven. The separate judge has not completed onboarding on a fresh account and verified a working personal mesh.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven. Public download alone is not onboarding, self-connect, or stranger task completion.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/5 verified, 0 percent. The public candidate `549322c` plus release `c0e8ca...` is pending judge and does not change this number.
- M2 packaged typed-input reality judge pass rate: 0/0 verified; not run.
- M3 packaged/browser-hands reality judge pass rate: 0/0 verified; not run.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: active. Builder-owned tests remain green while M1 reality pass rate is 0 percent. Do not advance M1, M2, M3, or M5 from local app launch, local packaging, public headers, public SHA checks, browser automation observations, owner Chrome observations, or screenshots without the separate judge seeing the clean production front door and real app artifact.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Treating any production-linked source or manifest commit, including `bb4319ab` or `549322c`, as M1, M2, M3, or M5 proof before the separate judge verifies the real public front door, public DMG, app launch, packaged typed task, browser/action artifact, or fresh-account onboarding path.
- Treating local tests, direct probes, mocked Playwright, browser automation page loads, public headers, public SHA checks, owner Chrome, local packaging, strict codesign, or screenshots as proof.
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
- Treating the local self-test endpoint, extension value read-back, extension zip hashes, refreshed Desktop extension folders, archive payload inspection, fake-network Calendar probes, mocked server branch probes, or Browser/Playwright renders as proof.
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Old audio-first M0 as the daily gate. Audio is a final exam after clean typed perimeter works.
- Do not auto-prompt macOS microphone permission on first launch. It is a user-action permission, not part of the M1 stranger first-view surface.

Next:
- When separate judge quota is available, run the separate M1 judge against public production site commit `549322cec573c8667e908c84a16c2736540d9e81` and release SHA `c0e8ca6778ce969fc32f02e7773ddb2026992c5162344132535f79182041f172`.
- If M1 passes, run an M2/M3 judge that types a safe, reversible, fully time-grounded task in the packaged app and verifies the real artifact or browser action.
- While judge quota is blocked, keep improving unblocked production-source perimeter slices without claiming proof.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Guards, abstention, ask-only behavior, public headers, owner/browser checks, and empty-plan completion are not progress. Missing context must be supplied. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
