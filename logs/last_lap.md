# Last Lap

Lap: 20260609T190603Z
Date: 2026-06-09T19:25:38Z
Milestone: M3 - Wayfair real-store support, deeper cart extraction, and no-duplicate retry hardening
ALL_MILESTONES_DONE: false

Judge verdict: UNPROVEN-PENDING-JUDGE, Tamper: NOT_RUN

What changed:
- WebVoyager now knows Wayfair search, product, and basket URL shapes.
- NativeBridgeLink now treats `keyword` search params as query tokens, ranks `/pdp/` product links as product-like, and keeps up to 25,000 characters of rendered text from direct CDP proof so deep cart item text is not silently truncated before proof.
- Cart element proof now accepts a matching cart-page product link slightly deeper in the first action marks only when it is near item-local cart controls such as `Remove` or `Quantity`, preserving the recommendation guard.
- BrowserHand now marks failed commerce runs with a real changed mutation as `non_retryable_real_mutation`, and the orchestrator honors that flag so it fails once instead of retrying and potentially adding the same item again.

Real runs:
- Read-only probes found Wayfair product rows, a real product page, Add to Cart controls, and `/v/checkout/basket/show`.
- A pre-no-retry live `/event` run seeded context-only memory, then sent a vague action that did not name Wayfair or the item. The task loop resolved Wayfair and the remembered item from memory, opened the product, clicked real Add to Cart, and final basket read-back matched the item after deeper text extraction and cart-element proof hardening. This run needed a retry and exposed duplicate-add risk, so it is not clean current-code proof.
- The current-code fresh live `/event` run resolved the same vague memory task, clicked a real Wayfair Add to Cart control, then failed closed after the known cart page did not verify the item. The new non-retry guard prevented a second add attempt. A delayed read-only cart probe still did not verify the item.
- No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Checks:
- `engine/.venv/bin/python -m py_compile engine/anticipy_engine/agent/webvoyager.py engine/anticipy_engine/core/native_bridge_link.py engine/anticipy_engine/core/orchestrator.py engine/anticipy_engine/hands/browser_hand.py` passed.
- Focused Wayfair URL, product identity, cart element proof, and recommendation counterexample checks passed.
- Focused non-retryable real mutation BrowserHand and orchestrator checks passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_hand.py` passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_handoff.py` passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Forbidden-path scan was clean.
- Secret-shaped diff scan was clean.
- Product/eval literal scan was clean.
- Ports `8787`, `7777`, and `9222` were clear after live runs.

Gate:
- No all-work human gate is active.
- Separate judge quota blocks proof only, not building.
- Wayfair is now supported at the URL/DOM recipe level and has one pre-no-retry builder-side cart read-back success plus one current-code fail-closed run. Treat it as `UNPROVEN-PENDING-JUDGE` and do not claim M3 done.

Proof status:
- M3 is not done.
- This lap is real-site support plus proof extraction and failure hardening. It is `UNPROVEN-PENDING-JUDGE`.
- Generalization remains UNPROVEN.

Next:
- Continue M3 ladder work only. Prefer another real store or a concrete persistence/read-back hypothesis. If a commerce mutation is unverified, do not retry the same action in the same goal.
