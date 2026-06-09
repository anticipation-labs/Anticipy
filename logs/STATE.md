# STATE

Current milestone: M3 only. UI, status, onboarding, observability, localhost, `example.com`, fixture, and no-stakes target laps are banned while this focus is active. The only allowed work is the hard browser-hand chain: vague natural-language task, memory resolves the real site and real item, the browser hand acts on that real site, a real reversible artifact changes, and the separate judge later verifies the change.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed the planted-fake self-check, computer-use self-test, diff scan, and different-family cross-check. It opened the clean public front door, downloaded the then-public DMG, mounted it, and launched the public app. The public app failed because strict codesign and `spctl --assess` failed with a resource-signature error, and launch produced an invisible app process with zero windows. Proof: `logs/verdicts/20260607T114534Z.md`.

Latest builder lap: `20260609T083504Z` is `UNPROVEN-PENDING-JUDGE`, not proof. It hardened rendered CDP page observation, stale selector click recovery, search/product URL handling, commerce wall detection, region interstitial handling, and product filtering. Real Best Buy, Walmart, Target, and IKEA attempts still did not create a judge-verified cart artifact, so M3 is not done.

Latest offline M3 slice:
- `NativeBridgeLink` can capture rendered text and visible actionable selectors from the exact live CDP target, avoiding static-shell-only observations on hydrated real stores.
- `NativeBridgeLink` preserves rendered hrefs, stores expected click metadata, and re-resolves stale selectors by expected name, role, or href after DOM re-renders.
- `NativeBridgeLink` brings the target page forward, dispatches CDP mouse events with button state, and applies a resolved-element JavaScript click fallback when local CDP input reports success without firing handlers.
- WebVoyager product URL recovery now uses rendered element `href` fields as well as href-only labels.
- WebVoyager recognizes real search-result URLs such as Best Buy `searchpage.jsp`, so a product click that stays on results can navigate the adjacent product URL.
- WebVoyager detects commerce walls after search, region selection, product open, and add observations, then hands off instead of faking progress.
- WebVoyager can select a visible United States region choice on store country interstitials.
- WebVoyager filters editorial/advice/category pages out of product selection. These filters prevent false product targets, but they are not M3 proof.
- Focused probes passed, but these are regression checks only. They are not M3 proof.

Latest real M3 attempt:
- A builder-visible memory note was sent through the live `/event` path.
- A vague kitchen shopping task was then sent through `/event`.
- The system resolved the vague request to Target and the remembered item without typing the whole instruction into search.
- Earlier real attempts exposed false or wrong actions: a context-only seed acted before the guard fix, and wrong variant or recommendation candidates were clicked before quantity and product-button hardening.
- After the fixes, a live Target run added the resolved Brita 6 Cup Water Filter Pitcher item through the browser hand and captured compact page-state evidence after the real add flow.
- This changed a real cart, but it remains `UNPROVEN-PENDING-JUDGE`. No separate judge has opened the account and ruled on it. M3 is not done.

Latest real bridge finding:
- Real Best Buy initially returned only a static shell through direct proof; rendered CDP snapshots fixed that and exposed the real search page with actionable elements.
- Real Best Buy then navigated to a matching product URL and clicked a product-page Add to cart control, but cart verification found an empty cart.
- Real Walmart navigated to a matching product URL and clicked a product-page Add to cart control with both trusted CDP and bridge click paths tested, but cart verification found an empty cart.
- Real Target opened the exact Brita product page and clicked Add to cart before and after stale-click recovery, but cart verification found an empty cart.
- Real IKEA exposed false product selection on an editorial how-to page and a category page; filters now block those, and the final IKEA run failed honestly by not identifying a buyable matching product within the recipe budget.
- No verified artifact exists. The next M3 slice should harden buyable-product extraction on rendered store pages and post-click mutation detection, then keep verifying only real cart state.

Current constraint:
- Current allowed work is M3 only.
- Low OpenRouter credit blocks the old heavy WebVoyager planning loop, not building. Continue with cached observations, deterministic real-store DOM recipes, item matching, compact page-state capture, native bridge transport work, and tiny-model decisions where needed.
- Judge quota blocks proof only. Spending money is a hard human gate and was not taken.

Latest product/public candidate, unchanged this lap:
- Public site build commit: `921f45bcc3789be479a72636b0245f7b0a1df514`.
- Public DMG source commit in manifest: `6ae2e9951619875c0ecc45bbce64c0b5620a75cc`.
- Public DMG SHA-256: `9e4e2ef71b8dcfbbc4cd6b6f390f2fbf835c3e4a85ab6e0d75f04fa286c5e03d`.
- Public DMG size: `178894746` bytes.
- Public R2 URL: `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/builds/6ae2e9951619875c0ecc45bbce64c0b5620a75cc/Anticipy_1.0.0_aarch64.dmg`.
- This is not M1, M2, M3, or M5 proof.

Latest checks, candidate evidence only:
- Mandatory compaction-proof reads were re-run for `00_AMENDMENT_NEVER_STALL.md`, `AGENTS.md`, `autopilot/02_LAWS.md`, `autopilot/09_REPO_FACTS.md`, `logs/STATE.md`, `autopilot/00_START_HERE.md`, `CODEX_BRIEF.md`, `logs/last_lap.md`, `autopilot/07_MILESTONES.md`, and `autopilot/LESSONS.md`.
- Python compile passed for the touched engine files.
- Focused commerce wall handling probe passed.
- Focused region selection probe passed.
- Live rendered Best Buy snapshot probe passed.
- Focused product href recovery probe passed.
- Focused search-results URL detection probe passed.
- Focused stale selector re-resolution probe passed.
- Focused content URL filtering probe passed.
- Focused category URL filtering probe passed.
- Real Best Buy, Walmart, Target, and IKEA attempts exercised real store pages but did not verify cart artifacts.
- `engine/scripts/test_browser_hand.py` passed.
- `engine/scripts/test_handoff.py` passed.
- `engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Forbidden-path scan, owner/eval literal scan, and secret-value scan found no matches.
- Ports 8787, 7777, and 9222 have no remaining listeners.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed in setup; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- M1 is not proven. The current public production app must be downloaded, installed, and launched by the separate judge from the clean public front door.
- M2 is not proven. The separate judge has not typed or uploaded through the packaged or public app and verified a real correct artifact.
- M3 is not proven. A prior real Target add run from `20260609T034900Z` changed a real cart, but no separate judge proof exists. The newest Best Buy, Walmart, Target, and IKEA CDP bridge attempts exercised real product/search/cart flows but did not verify a cart artifact.
- M5 is not proven. The separate judge has not completed onboarding on a fresh account and verified a working personal mesh.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven.

Gate status:
- No all-work human gate is active.
- Target sign-in blocked that specific store path in the dedicated Chrome profile, but a hard site is not an all-work stop.
- Low OpenRouter credit is not a stop. It requires cheaper M3 planning and deterministic browser action hardening.
- Separate Codex CLI usage for independent builder/judge sessions is exhausted until the reported reset on June 12, 2026 at 5:34 PM local time unless money is spent. This blocks separate proof only. Spending money is a hard human gate and was not taken.
- Apple Developer ID signing and notarization are unavailable on this Mac: `security find-identity -v -p codesigning` reports 0 valid identities.
- Owner Chrome has Anticipy extension id `npnpagopediecennpleihemoochikggb` registered at `/Users/omarebrahim/Desktop/Anticipy-Extension`, but disabled.
- Possible cleanup item: a native Apple Calendar smoke may have created `[Anticipy test] M2 typed smoke 20260607-continue` on June 12, 2026 from 15:00 to 16:00. Local read-back and deletion were blocked by macOS privacy/TCC and AppleScript list timeouts. This remains queued in `PENDING_FOR_OMAR.md`; do not delete or modify real existing Calendar data.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Clean typed M0 reality judge pass rate: 1/3 verified, 33 percent.
- M1 reality judge pass rate: 0/5 verified, 0 percent.
- M2 packaged/public typed-input/listen-control/clock-grounding/status/audio-upload/status-failure reality judge pass rate: 0/0 verified; not run.
- M3 real browser-hand reality judge pass rate: 0/1 unjudged builder artifact verified, 0 percent. Latest real Best Buy, Walmart, Target, and IKEA attempts did not verify a cart artifact; the prior real Target add-to-cart attempt changed a real cart but has no separate judge verdict.
- M5 packaged/self-onboarding reality judge pass rate: 0/0 verified; not run.
- Amended pre-clean audio reality judge pass rate: 0/10 verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet.
- Drift siren: active. Builder-owned tests remain green while reality pass rates remain flat.

Realday audio:
- One timestamped student MP3 and a builder-visible transcript are in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. The builder must never read them.
- Audio transcription is sidecar-cached. Held-out sidecars are judge-only. The inner loop must use typed input or cached text and complete in minutes.
- The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Do not work on UI/status/onboarding/perimeter polish while the hard M3-only amendment is active.
- Do not use `example.com`, localhost, fixture pages, or contrived no-stakes pages as M3 targets or evidence.
- Do not type the whole task into browser search or the address bar for action tasks.
- Do not treat context-only memory observations as tasks. A separate action-shaped request must arrive before acting.
- Do not trust loose numeric item matching on real stores. Quantity and unit details must match exact variants before opening products or clicking product-specific add controls.
- Do not click recommendation add buttons unless their label strongly matches the requested product.
- Do not let unquoted memory item extraction swallow site/context text into the item, and do not put raw memory source text into browser job args.
- Do not let a vague request with contextual hints act on a remembered cart target whose memory line does not match those hints.
- Do not let direct cart phrasing become whole-task browser search. Extract the concrete resolved item only, and reject unresolved vague placeholders before the browser recipe runs.
- Do not click generic `Add to cart` controls on search results when no matching product has been identified. Open the matching product first, or require the add label to strongly name the requested item.
- Do not continue from an unverified item-specific result-page add into another product. Verify the cart, open cart if a cart control exists, or stop with a real failure.
- Do not switch products after an unverified add. If continuing, open only the adjacent matching product URL tied to the same add/title.
- Do not open href-only product anchors as primary product choices. Prefer readable product names or product-specific add controls, and use adjacent hrefs only as a fallback for the same matched product.
- Do not treat an add click as proof. Open the real cart and require the requested item tokens in cart state.
- Do not retry Target blindly in the dedicated profile without handling its login redirect after product-page add.
- Do not assume Walmart product-page add mutates cart just because the add control was clicked. It must verify in real cart state.
- Do not accept top-navigation-only bridge observations for search pages. Wait for query-matching actionable marks.
- Do not accept static-shell-only bridge observations on hydrated real stores. Use rendered CDP text and visible actionable marks from the exact target.
- Do not trust stale data-index selectors after real-store DOM re-renders. Re-resolve by expected role, name, or href at click time and verify page mutation or cart state.
- Do not open loosely related product titles before an add attempt. Two-token items must match both tokens, and longer item names need a stronger token majority.
- Do not treat editorial, advice, how-to, or category pages as buyable product pages for add-to-cart recipes.
- Do not verify a product-page add from broad page text. For non-cart URLs, the requested item and quantity/unit must match near the cart marker, and recommendation/similar-item text after the marker must not count.
- Do not let price-preference words become product identity tokens. `Cheapest`, `lowest priced`, `budget`, and similar words guide candidate ranking, but the browser search and item match must use only the concrete resolved item.
- Do not keep spending OpenRouter calls through the old heavy planner when credit only permits tiny output caps. Make the browser hand cheaper, deterministic where possible, and cache page observations instead.
- Do not claim M3 progress from self-tests, mocks, status displays, public renders, screenshots alone, or browser diagnostics.
- Do not treat a screenshot-only AppleScript bridge observation as actionable. It must expose elements/selectors or the real chain must fail fast.
- Do not run broad searches over `.env.local`, env backup files, raw Chrome profiles, or `.anticipy` state. Search only targeted code files.
- Do not run a production `next build` while reusing an active Next dev server for rendered checks.
- Do not treat public source, manifest commit, public headers, public SHA, release metadata, page render, local packaging, local launch, owner Chrome, screenshot, or process/window enumeration as M1, M2, M3, or M5 proof before separate judge verification.
- Do not assume in-app Browser is healthy after stale logs or native-pipe failures. Try it once when the browser skill requires it, record the result, then use a scoped fallback only for non-proof diagnostics.
- Do not run old `scripts/ship.sh` blindly. Use `scripts/ship_candidate.sh` and never push.
- Do not let stale untracked `public/Anticipy.dmg` enter Vercel output.
- Do not make product changes in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` without a tracked, judgeable product commit in that source tree.
- Do not use native local Apple Calendar as autonomous proof when read-back and cleanup are blocked.
- Do not dump raw Chrome profile preference files or local env files.
- Google Sheets and Google Docs canvas synthetic input remain dead ends.
- Amazon.ca Playwright automation remains a dead end.
- Do not escalate anti-bot arms races for captcha or Cloudflare challenges.
- Do not design always-on cloud transcription.
- Old audio-first M0 is not the daily gate.

Next:
- Continue immediately on the hard M3 chain despite low live credit and judge quota. Do not work UI/status/onboarding.
- Harden buyable-product extraction on rendered real-store pages and post-click mutation detection. Distinguish product, category, and editorial surfaces, capture add-click return state, and keep verifying only through real cart state. Every run remains `UNPROVEN-PENDING-JUDGE` until the separate judge verifies it.

Law digest:
Read `00_AMENDMENT_NEVER_STALL.md` first. Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Never park on judge quota, low credit, or a hard site. M3 only: vague task, memory-resolved real site and item, browser hand changes a real reversible artifact, separate judge verifies. No contrived pages, no search-bar task dumping, no mocks as progress. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git.
