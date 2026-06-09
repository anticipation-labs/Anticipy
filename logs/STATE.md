# STATE

Current milestone: M3 only. UI, status, onboarding, observability, localhost, `example.com`, fixture, and no-stakes target laps are banned while this focus is active. Allowed work is the hard browser-hand chain: vague natural-language task, memory resolves the real site and real item, the browser hand acts on that real site, a real reversible artifact changes, and the separate judge later verifies the change.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed self-checks and opened the public front door, but the public app failed strict signing/launch verification. Proof: `logs/verdicts/20260607T114534Z.md`.

Latest builder lap: `20260609T092904Z` is `UNPROVEN-PENDING-JUDGE`, not proof. It hardened duplicate-safe real-store cart read-back. WebVoyager now parses cart counts, rejects zero-count cart pages before item matching, filters recommendation/sponsored/similar/related text out of cart-page item matching, records `cart_count` in page-state traces, and preflights known real cart URLs before any Add click. If the real cart page already contains the requested item, it returns `already_in_cart=true` and avoids adding a duplicate.

Current M3 slice:
- `NativeBridgeLink` can capture rendered text and visible actionable selectors from the exact live CDP target, preserving hrefs and re-resolving stale selectors by role, name, or href.
- WebVoyager can distinguish search, product, content/category/editorial, cart, login, and checkout surfaces on known commerce hosts.
- WebVoyager prefers buyable product URLs and rejects known non-product hrefs before opening a candidate.
- WebVoyager records add-click mutation evidence, but final commerce success requires cart-page verification. Product-page modals, search-result text, zero-count cart labels, transient cart badges, and screenshots alone do not complete a cart task.
- WebVoyager now preflights the known cart page before add clicks and avoids duplicate additions when the cart already contains the requested item.
- Memory-to-intent item cleanup strips the resolved site's host stem and dangling site prepositions, so browser search receives the concrete item rather than the item plus store words.

Latest real M3 attempt:
- A fresh ignored data directory was used for a builder-side live `/event` run.
- A context-only memory seed was captured and triaged out, so it did not act by itself.
- A vague request resolved from memory to site `https://lowes.com` and item `spray bottle`.
- The browser hand opened the real Lowe's cart page as preflight, found `cart_count=3`, `cart_page_verified=true`, and returned `already_in_cart=true`.
- The run history contained only the known-cart preflight navigation, so it did not click Add again and did not duplicate the cart item.
- This is a real builder-side cart read-back and remains `UNPROVEN-PENDING-JUDGE`. No separate judge has opened the site/account and ruled on it. M3 is not done.

Latest real bridge findings:
- IKEA search-results add changed a transient shopping-bag count, but the known cart page did not contain the requested item. This is a failure, not proof.
- Home Depot returned only a privacy surface with no product tokens or buyable links. This is a hard-site finding, not proof.
- Lowe's direct recipe opened a buyable product page, clicked Add to Cart, opened `/cart`, and matched the requested item there. A later full `/event` run read the existing cart item by preflight and avoided another add.
- Earlier Best Buy, Walmart, Target, and IKEA attempts exposed static-shell observations, stale selectors, wrong product/category/editorial selection, non-mutating add clicks, and empty-cart read-backs. Do not retry those blindly.

Current constraints:
- Current allowed work is M3 only.
- Low OpenRouter credit blocks the old heavy WebVoyager planning loop, not building. Continue with deterministic memory resolution, deterministic real-store DOM recipes, cached observations, compact page-state capture, and tiny-model decisions only where needed.
- Judge quota blocks proof only. Spending money is a hard human gate and was not taken.

Latest checks:
- Mandatory compaction-proof reads were re-run for `00_AMENDMENT_NEVER_STALL.md`, `AGENTS.md`, `autopilot/02_LAWS.md`, `autopilot/09_REPO_FACTS.md`, `logs/STATE.md`, `autopilot/00_START_HERE.md`, `CODEX_BRIEF.md`, `logs/last_lap.md`, `autopilot/07_MILESTONES.md`, and `autopilot/LESSONS.md`.
- Python compile passed for the touched engine file.
- Focused cart-preflight probe passed: zero-count cart rejected, real cart URL accepted, duplicate add skipped without model calls.
- Real live `/event` run completed through the Lowe's cart preflight and did not duplicate the item. Builder-side only.
- `engine/scripts/test_browser_hand.py` passed.
- `engine/scripts/test_handoff.py` passed.
- `engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Changed product file scan found no forbidden owner/eval literals and no exact key names or secret-shaped values.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed in setup; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- M1 is not proven. The current public production app must be downloaded, installed, and launched by the separate judge from the clean public front door.
- M2 is not proven. The separate judge has not typed or uploaded through the packaged or public app and verified a real correct artifact.
- M3 is not proven. Prior Target and current Lowe's builder-side runs changed or read real carts, and the current Lowe's full `/event` path ended at real `/cart` with cart-page verification, but no separate judge proof exists.
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
- M2 reality judge pass rate: 0/0 verified, not run.
- M3 real browser-hand reality judge pass rate: 0/2 unjudged builder artifacts verified, 0 percent. Prior Target and current Lowe's builder-side cart artifacts or read-backs exist, but no separate judge has verified either artifact.
- M5 reality judge pass rate: 0/0 verified, not run.
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
- Do not click generic `Add to cart` controls on search results when no matching product has been identified. Open the matching product first, or require the add label to strongly name the requested item.
- Do not treat an add click as proof. Open the real cart and require the requested item tokens in cart state.
- Do not accept product-page add modals, search-result pages, zero-count cart labels, transient cart badges, or screenshots alone as final cart proof.
- Do not duplicate an item already present in the cart during repeated builder runs. Read the known cart page first and use `already_in_cart=true` only if cart-page verification passes.
- Do not let memory item extraction keep the store name or a dangling `on/from/at` site phrase inside the item.
- Do not trust stale data-index selectors after real-store DOM re-renders. Re-resolve by expected role, name, or href at click time and verify page mutation or cart state.
- Do not open loosely related product titles before an add attempt. Two-token items must match both tokens, and longer item names need a stronger token majority.
- Do not treat editorial, advice, how-to, or category pages as buyable product pages for add-to-cart recipes.
- Do not keep spending OpenRouter calls through the old heavy planner when credit only permits tiny output caps.
- Do not claim M3 progress from self-tests, mocks, status displays, public renders, screenshots alone, or browser diagnostics.
- Do not run broad searches over `.env.local`, env backup files, raw Chrome profiles, `.anticipy` state, or raw local data.
- Google Sheets and Google Docs canvas synthetic input remain dead ends.
- Amazon.ca Playwright automation remains a dead end.
- Do not escalate anti-bot arms races for captcha or Cloudflare challenges.
- Do not design always-on cloud transcription.

Next:
- Convert the current Lowe's `UNPROVEN-PENDING-JUDGE` artifact and duplicate-safe cart read-back through the separate judge when quota returns.
- Until then, continue real M3 ladder work: quantity/cart cleanup awareness, variant-safe product selection, broader real-store recipes, and failure hardening on real cart read-back.

Law digest:
Read `00_AMENDMENT_NEVER_STALL.md` first. Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Never park on judge quota, low credit, or a hard site. M3 only: vague task, memory-resolved real site and item, browser hand changes or safely verifies a real reversible artifact, separate judge verifies. No contrived pages, no search-bar task dumping, no mocks as progress. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git.
