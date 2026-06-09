# Last Lap

Lap: 20260609T091008Z
Date: 2026-06-09T09:24:25Z
Milestone: M3 - memory-resolved real-store cart action
ALL_MILESTONES_DONE: false

Judge verdict: UNPROVEN-PENDING-JUDGE, Tamper: NOT_RUN

What changed:
- WebVoyager now classifies known commerce product URLs separately from search, category, editorial, login, checkout, and cart URLs. Known stores use product-path patterns such as product, item, or product-detail paths; unknown stores still fall back to generic product URL hints.
- Product picking now prefers buyable product hrefs and rejects known non-product hrefs before opening a candidate.
- Add-to-cart clicks now record mutation evidence: URL change, title change, page digest change, cart-signal change, and whether the observed state is cart-verified.
- Final commerce completion now requires cart-page verification. Product-page add modals, nav badges, search-result text, screenshots, or zero-count cart labels cannot complete a cart task.
- The memory-to-intent item sanitizer now strips the resolved site's host stem and dangling site prepositions from remembered item text, so a memory line like a product on a store resolves to the product, not the product plus store name.

Real runs:
- IKEA search-results add changed a transient shopping-bag count, but the known cart page did not contain the item. This was treated as a failure, not proof.
- Home Depot returned only a privacy surface with no product tokens or buyable links. This was treated as a hard-site failure, not proof.
- Direct Lowe's recipe opened a real product page, clicked a real Add to Cart control, opened the real `/cart` page, and cart-page verification matched the item. Builder-side only.
- Full `/event` run with a fresh ignored data directory: the context-only memory seed was captured and triaged out, the vague garage request resolved from memory to Lowe's and the spray bottle, the browser hand opened a real product page, clicked Add to Cart, opened real `/cart`, and the goal finished `done` from cart-page verification. This remains `UNPROVEN-PENDING-JUDGE`; no separate judge verified it.

Checks:
- Mandatory control-plane reload completed from disk.
- Python compile passed for touched engine files.
- Focused probes passed for product URL classification, cart badge mutation scoring, zero-count cart false-positive rejection, strict cart-page completion, and memory item sanitization.
- `engine/scripts/test_browser_hand.py` passed.
- `engine/scripts/test_handoff.py` passed.
- `engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Changed product file scan found no forbidden paths, no owner/eval literals, and no obvious secret-shaped values.

Gate:
- No all-work human gate is active.
- Separate judge quota still blocks proof only, not building. Spending money remains a human gate and was not taken.
- Low model credit did not block the lap because the real path used deterministic memory resolution and deterministic store DOM recipes.

Proof status:
- A real Lowe's cart artifact was created and read back by the builder-side live engine path.
- M3 is not done because the separate judge has not opened the real account/site and verified the artifact.
- Generalization remains UNPROVEN.

Next:
- Continue M3 ladder work. Convert this `UNPROVEN-PENDING-JUDGE` cart artifact through the separate judge when quota returns. Until then, keep hardening the real chain: reduce duplicate cart additions, improve cleanup/quantity awareness, broaden real-store product recipes, and keep final success tied to cart-page read-back.
