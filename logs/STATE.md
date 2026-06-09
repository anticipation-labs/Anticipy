# STATE

Current milestone: M3 only. UI, status, onboarding, observability, localhost, `example.com`, fixture, and no-stakes target laps are banned while this focus is active. Allowed work is the hard browser-hand chain: vague natural-language task, memory resolves the real site and real item, the browser hand acts on that real site, a real reversible artifact changes or is safely verified, and the separate judge later verifies the change.

Latest judged lap: `20260607T114534Z` was `FAKE` with `Tamper: NO`. The separate M1 judge passed self-checks and opened the public front door, but the public app failed strict signing/launch verification. Proof: `logs/verdicts/20260607T114534Z.md`.

Latest builder lap: `20260609T140258Z` is `UNPROVEN-PENDING-JUDGE`, not proof. It hardened exact product selection and CDP startup for fresh browser profiles. WebVoyager now scores compact ordered item-token sequences, removes long-title ranking rewards, treats URL/title-only observations with no text or actionable elements as not ready, and retries empty search surfaces before failing. `NativeBridgeLink` now creates the configured Chrome user-data directory before CDP launch, so fresh per-lap profiles can return actionable marks. Real Target work found one safe no-add failure, one broad-substitute false action before the ranking fix, and one no-marks capture-layer failure before profile-dir creation. After the fixes, a sanitized direct Target probe saw 299 actionable elements and 131 product-like links, and the final live `/event` run resolved a vague memory task to Target plus `OXO Dish Brush`, opened exact product `/p/oxo-dish-brush/-/A-80221510`, clicked a real Add to cart control, opened Target cart, and durable cart read-back matched the item. No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Current M3 slice:
- `NativeBridgeLink` can capture rendered text and visible actionable selectors from the exact live CDP target, preserving hrefs and re-resolving stale selectors by role, name, or href.
- `NativeBridgeLink` scrolls the active CDP page target before falling back to the native bridge scroll command, keeping scroll actions aligned with later proof reads.
- WebVoyager distinguishes search, product, content/category/editorial, cart, login, and checkout surfaces on known commerce hosts.
- WebVoyager prefers buyable product URLs and rejects known non-product hrefs before opening a candidate.
- WebVoyager records add-click mutation evidence, but final commerce success requires cart-page verification. Product-page modals, search-result text, zero-count cart labels, transient cart badges, screenshots alone, and broad cart text are not completion proof.
- WebVoyager requires cart URL item evidence to appear with cart item structure such as checkout, subtotal, quantity, remove, shipping, pickup, or delivery. Navigation-only category text on a cart shell cannot prove completion.
- WebVoyager preflights known cart pages before add clicks and avoids duplicate additions when the cart already contains the requested item.
- WebVoyager verifies cart pages through distinct item evidence windows, including token-hit counts and explicit quantity when visible, while keeping raw cart text out of durable state.
- WebVoyager carries memory context hints into product selection and can fall back from strict token matching to first valid product URLs only on real search-result pages.
- Memory-to-intent item cleanup strips the resolved site's host stem and dangling site prepositions, recognizes generic shopping comparison/research memories, and strips leading room-context words only when at least two product words remain while preserving context hints.
- WebVoyager treats bare `Options` and broader option-control phrases as generic product labels, preventing option controls from becoming concrete product targets before add attempts.
- WebVoyager rejects shopping-list, wishlist, favorite, registry, save-for-later, and remove controls as product targets.
- WebVoyager refreshes a settled product page once before scrolling for add controls, so late-rendered real Add to Cart buttons can be found without heavy model planning.
- WebVoyager recognizes both legacy `/site/.../*.p` and current `/product/...` Best Buy product URLs as buyable product URLs.
- WebVoyager cart proof splits item matching at order-summary, checkout, and recommendation boundaries and uses tighter local item evidence windows so recommendation products cannot satisfy final cart proof.
- WebVoyager accepts non-generic item-specific Add labels using the same required product-hit threshold as product-title matching, so two-token items can use real labels without allowing unrelated items.
- WebVoyager knows Office Depot search, product, and cart URL shapes. Office Depot remains an unproven hard site because both product-page Add and adjacent result-row Add failed final cart verification.
- WebVoyager can click a generic search-result Add only when it is adjacent to a strongly matched product row, ignores ratings/review links as product boundaries unless their visible label carries item-token evidence, requires known-cart verification, and fails instead of attempting a duplicate fallback.
- WebVoyager knows REI search, product, and cart URL shapes. REI builder-side cart read-back works for an exact remembered item under strict cart-structure proof, but no separate judge has verified it.
- WebVoyager knows PetSmart and Container Store search, product, and cart URL shapes. PetSmart and Container Store are unproven hard-site candidates, not judge proof.
- WebVoyager classifies narrow domain-specific product URL matches before broad search/content rejection and runs product-surface detection before search-surface detection for those matches.
- NativeBridgeLink exposes `fresh_probe()`, and WebVoyager native-bridge known-cart preflight must survive that independent observer before it can complete. Same-bridge cart state is not durable proof.
- WebVoyager active-page cart completions after search-result add, product-page add, refresh, scroll, or View Cart must also survive independent `fresh_probe` confirmation before they can complete.
- WebVoyager scrolls cart pages during known-cart and fresh-probe read-back, keeping the highest-signal cart observation instead of trusting a header-only cart count.
- WebVoyager requires leading distinctive tokens for token-rich remembered items and raises the product-hit threshold to roughly 80 percent for item names with five or more tokens.
- WebVoyager requires distinctive-token agreement when selecting nearby product URLs and adjacent search-result Add controls.
- WebVoyager checks visible product-page identity before product-page Add attempts. Visible title/text/labels must satisfy the token threshold and leading distinctive tokens by themselves; URL tokens are supportive metadata only and cannot rescue a contradictory visible page.
- WebVoyager ranks product candidates with a compact ordered item-token score and no longer rewards longer titles when token hits tie, so exact ordered product names beat broad titles with scattered requested tokens.
- WebVoyager treats navigated URL/title-only observations with no text or actionable elements as not ready, and commerce search surfaces get bounded re-observe or scroll retries before failing as unactionable.
- `NativeBridgeLink` creates the configured `ANTICIPY_CHROME_USER_DATA_DIR` before CDP launch, enabling fresh per-lap Chrome profiles to return real actionable marks.
- The orchestrator marks exhausted worker retries as failed. True human gates still return `needs_human` directly from the hand, but ordinary hard-site failures no longer park the goal as waiting.

Latest real M3 attempt:
- Fresh ignored data directories and fresh Chrome user-data directories were used for builder-side live `/event` runs.
- A Target run with a remembered item that included a missing sub-brand failed safely without an Add click.
- A pre-ranking-fix Target run resolved a vague memory task to Target plus the visible item name but selected a broader soap-dispensing palm brush product and verified broad cart text. This is counted as a broad-substitute false action, not progress.
- A post-ranking rerun still failed safely because the fresh Chrome profile directory did not exist, CDP did not start, and the bridge saw zero actionable Target marks.
- After profile-dir creation, a sanitized direct Target probe saw 299 actionable elements and 131 product-like links.
- The final live `/event` run used context-only memory plus a vague action that did not name the site or exact item. The hand resolved Target plus `OXO Dish Brush`, opened exact product `/p/oxo-dish-brush/-/A-80221510`, clicked a real Add to cart control, opened Target cart, and durable cart read-back matched the item. This is builder-side only and remains `UNPROVEN-PENDING-JUDGE`.
- No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Latest real bridge findings:
- Target can complete real search-product-add-cart-verify and duplicate-safe known-cart verification paths for vague memory-resolved tasks in the dedicated browser path.
- Walmart can complete real search-product-add-cart-verify paths for vague memory-resolved tasks after generic option labels are skipped and settled product pages are refreshed before add-control scrolling.
- Best Buy can complete a real search-product-add-cart-verify path for a vague memory-resolved task after current `/product/...` URLs are accepted.
- Lowe's can complete some real full `/event` vague-memory cart add paths and duplicate-safe known-cart read-backs, but token-rich exact-item paths exposed broad substitute and contradictory-page failures. The latest visible-identity guard blocks the observed contradictory-page Add before mutation, but the gloves path remains a false-action hard finding until a new exact-product hypothesis is proven.
- IKEA can use a search-result item-specific Add path when product pages are availability-gated, while keeping strict final cart proof.
- REI can expose product links and cart structure through the bridge, and builder-side read-back can verify an exact remembered cart item under strict proof.
- PetSmart exposes product pages and Add controls through the bridge, but the observed Add path did not verify a durable cart artifact.
- Container Store exposes product URLs and Add controls through the bridge, but active-bridge cart preflight was not durable under independent read-back, and the post-hardening rerun hit a captcha-class wall.
- Home Depot returned only a privacy surface with no product tokens or buyable links. This is a hard-site finding, not proof.
- Office Depot exposes product and add controls, but its add paths did not verify the known cart page. This is a hard-site finding and not proof.
- Staples search exposed no actionable product marks through the bridge after settling. This is a hard-site finding and not proof.

Current constraints:
- Current allowed work is M3 only.
- Low OpenRouter credit blocks the old heavy WebVoyager planning loop, not building. Continue with deterministic memory resolution, deterministic real-store DOM recipes, cached observations, compact page-state capture, and tiny-model decisions only where needed.
- Judge quota blocks proof only. Spending money is a hard human gate and was not taken.

Latest checks:
- Mandatory compaction-proof reads were re-run for `00_AMENDMENT_NEVER_STALL.md`, `AGENTS.md`, `autopilot/02_LAWS.md`, `autopilot/09_REPO_FACTS.md`, `logs/STATE.md`, `autopilot/00_START_HERE.md`, `CODEX_BRIEF.md`, `logs/last_lap.md`, `autopilot/07_MILESTONES.md`, and `autopilot/LESSONS.md`.
- Real live `/event` runs exercised the Target vague-memory path with exact-product ranking and CDP profile-dir hardening. One pre-fix broad-substitute Add was counted as a false action; the final post-fix run selected the exact Target product and verified durable cart read-back builder-side.
- `engine/.venv/bin/python -m py_compile engine/anticipy_engine/agent/webvoyager.py engine/anticipy_engine/core/orchestrator.py engine/anticipy_engine/core/native_bridge_link.py engine/anticipy_engine/hands/browser_hand.py` passed.
- Focused ordered-product ranking check passed.
- Focused Chrome profile directory creation check passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_hand.py` passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_handoff.py` passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Forbidden-path scan was clean.
- Secret-shaped diff scan was clean.
- Product diff eval-literal scan was clean.
- Ports `8787`, `7777`, and `9222` are clear.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed in setup; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- M0 clean floor is proven once: `logs/verdicts/20260607T032947Z.md` verifies one real typed Calendar task with connector read-back, screenshot proof, different-family cross-check, clean diff scan, and cleanup.

Not proven:
- M1 is not proven. The current public production app must be downloaded, installed, and launched by the separate judge from the clean public front door.
- M2 is not proven. The separate judge has not typed or uploaded through the packaged or public app and verified a real correct artifact.
- M3 is not proven. Target, Lowe's, Walmart, Best Buy, IKEA, and REI builder-side cart artifacts or read-backs exist, but no separate judge proof exists.
- M5 is not proven. The separate judge has not completed onboarding on a fresh account and verified a working personal mesh.
- Generalization is UNPROVEN.
- Raw audio inference is not proven and is not the daily gate.
- The full stranger path is not proven.

Gate status:
- No all-work human gate is active.
- Target, Walmart, Lowe's, Best Buy, IKEA, and REI can create or verify safe cart artifacts builder-side on some item shapes. Lowe's token-rich gloves produced one pre-fix false action this lap, then the tightened visible-identity guard rejected the repeat before Add. PetSmart and Container Store produced hard-site findings in the prior lap. Other hard-site failures are not all-work stops.
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
- M3 real browser-hand reality judge pass rate: 0/26 unjudged builder-side cart attempts, artifacts, or read-backs verified by the separate judge, 0 percent. Prior Target, Lowe's, Walmart, Best Buy, IKEA, and REI builder-side cart artifacts or read-backs exist, and PetSmart, Container Store, Office Depot, Staples, and Lowe's visible-identity findings exist, but no separate judge has verified M3.
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
- Do not click generic `Add to cart` controls on search results when no matching product has been identified. Open the matching product first, or require adjacency to a strongly matched product row.
- Do not treat an add click as proof. Open the real cart and require the requested item tokens in localized cart item evidence with real cart item structure.
- Do not accept product-page add modals, search-result pages, zero-count cart labels, transient cart badges, broad cart-page text, navigation-only cart shells, same-bridge active-target cart state, or screenshots alone as final cart proof.
- Do not duplicate an item already present in the cart during repeated builder runs. Read the known cart page first and use `already_in_cart=true` only if cart-page verification passes.
- Do not let memory item extraction keep the store name or a dangling `on/from/at` site phrase inside the item.
- Do not trust stale data-index selectors after real-store DOM re-renders. Re-resolve by expected role, name, or href at click time and verify page mutation or cart state.
- Do not open loosely related product titles before an add attempt. Two-token items must match both tokens, and longer item names need a stronger token majority.
- Do not treat bare `Options`, `Choose options`, `Select product options`, `View options`, or similar option-control labels as product targets. They are generic controls, not product identity.
- Do not treat shopping-list, wishlist, favorite, registry, save-for-later, or remove controls as product targets.
- Do not let recommendation products after an order summary, checkout block, or recommendation section satisfy cart proof.
- Do not let navigation/category words on a cart shell satisfy cart proof without cart item structure.
- Do not keep leading room-context words such as kitchen/bathroom/office inside the resolved item when at least two product words remain; keep them as context hints instead.
- If a product page has item evidence but no Add to Cart control on the first observation, refresh the settled product page once before scrolling. Some real stores render the Add control after the product page text appears.
- When a real search page has strong product titles but `buyable_product_links=0`, inspect sanitized href shapes and update the product URL classifier. Do not keep treating the store as linkless if the URL pattern drifted.
- If a real store search page returns synonym titles that do not contain the original query tokens, use the cautious search-result fallback only on search-result URLs and only for buyable product URLs. Do not use it on category, editorial, recommendation, or product pages.
- Do not treat editorial, advice, how-to, or category pages as buyable product pages for add-to-cart recipes.
- Some IKEA product pages expose only availability/ZIP checks and no Add control. Move sideways to a search-result add path or another item rather than forcing location changes.
- Non-generic item-specific Add labels must use the product-hit threshold, not a fixed minimum of 3, so two-token items can use real Add labels without allowing unrelated items.
- Price-suffixed generic Add labels are product-page controls only unless the surrounding search-result adjacency rules identify the exact product row.
- Native-bridge known-cart proof must survive an independent `fresh_probe()` observer. If the active bridge sees a cart item but fresh_probe does not, reject the proof and continue or fail honestly.
- Container Store hit a captcha-class wall after separate-probe hardening. Treat that path as a site-specific gate, not an all-work stop, and move sideways unless there is a new non-gated hypothesis.
- Active-page cart proof also needs independent fresh-probe confirmation. Do not complete after a product-page add modal, View Cart click, or scrolled cart page unless fresh_probe verifies the same item.
- For long, token-rich remembered items, do not add a product that keeps only brand plus category or category plus material. Important modifiers must remain present, or the correct action is failure.
- Do not let product URL slugs or hrefs supply missing identity tokens when the visible product title/text/labels disagree. Visible product identity must clear the item threshold before any real Add click.
- Do not reward long product titles when token hits tie. Compact ordered item phrases should beat broad titles with scattered requested tokens.
- Do not assume a fresh Chrome user-data directory exists. If `ANTICIPY_CHROME_USER_DATA_DIR` is configured, create it before CDP launch or the bridge may fall back to weak no-mark observations.
- Do not retry the Lowe's token-rich gloves path blindly. It produced wrong or unverified cart additions and needs a new exact-product or cart-readback hypothesis first.
- Do not keep spending OpenRouter calls through the old heavy planner when credit only permits tiny output caps.
- Do not retry Office Depot blindly. Product-page Add and adjacent result-row Add both changed the page but did not verify the known cart artifact; retry only with a new concrete cart-readback or modal hypothesis.
- Do not treat exhausted browser retries as a human gate. If the hand did not explicitly return `needs_human`, the step should fail honestly.
- Do not treat Staples as supported from the current bridge path. It returned no actionable product marks after settling.
- Do not claim M3 progress from self-tests, mocks, status displays, public renders, screenshots alone, or browser diagnostics.
- Do not run broad searches over `.env.local`, env backup files, raw Chrome profiles, `.anticipy` state, or raw local data.
- Google Sheets and Google Docs canvas synthetic input remain dead ends.
- Amazon.ca Playwright automation remains a dead end.
- Do not escalate anti-bot arms races for captcha or Cloudflare challenges.
- Do not design always-on cloud transcription.

Next:
- Convert the current Target exact-item path plus prior Best Buy, Walmart, Lowe's, IKEA, REI, and any future `UNPROVEN-PENDING-JUDGE` artifacts and duplicate-safe cart read-backs through the separate judge when quota returns.
- Until then, continue real M3 ladder work. Build exact item matching, independent read-back proof, and failure hardening without UI/status/onboarding work. Prefer a new real store or a concrete new hypothesis over blind retries on Office Depot, PetSmart, Container Store, Staples, or Lowe's token-rich gloves.

Law digest:
Read `00_AMENDMENT_NEVER_STALL.md` first. Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Never park on judge quota, low credit, or a hard site. M3 only: vague task, memory-resolved real site and item, browser hand changes or safely verifies a real reversible artifact, separate judge verifies. No contrived pages, no search-bar task dumping, no mocks as progress. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git.
