# Last Lap

Lap: 20260609T204214Z
Date: 2026-06-09T20:57:34Z
Milestone: M3 - Ace and ThriftBooks hard-site work plus product-selection hardening
ALL_MILESTONES_DONE: false

Judge verdict: UNPROVEN-PENDING-JUDGE, Tamper: NOT_RUN

What changed:
- WebVoyager now knows Ace Hardware search, product, and cart URL shapes: `/search?query=...`, `/cart`, and `/departments/.../<id>`.
- WebVoyager now knows ThriftBooks search, product, and cart URL shapes: `/browse/?b.search=...`, `/shopping-cart/`, and `/w/<slug>/<id>/`.
- Generic search-result detection recognizes ThriftBooks `browse` and `b.search` surfaces, and cart detection recognizes `/shopping-cart/`.
- Product selection now rejects `Unselect ... filter` controls as non-product controls, ignores href-less non-link buttons as product-open candidates, and applies a stronger penalty to unrequested variant words such as workbook and guide.

Real runs:
- Read-only probes checked iHerb and ThriftBooks after Ace failed. iHerb exposed many real product/Add/cart surfaces but the top results were broad substitutes for the requested brand, so it was not selected for a live action.
- Ace Hardware live `/event` used context-only memory plus a vague action that named neither Ace nor the item. The chain resolved the remembered kitchen item, opened the exact Ace product page, clicked a real `ADD TO CART`, opened `/cart`, and then failed final durable cart proof. A separate read-only cart probe on the same fresh profile saw only the cart shell and no item evidence. Ace is a hard-site/non-durable-cart finding, not proof.
- ThriftBooks first live `/event` used context-only memory plus a vague action that named neither ThriftBooks nor the book. It failed safely before mutation after selecting a workbook variant. This exposed the filter-control and variant-ranking selection bug.
- After hardening, a fresh ThriftBooks live `/event` resolved the remembered book, opened the base product page, clicked a real `Add to Cart`, opened `/shopping-cart/`, and failed final durable cart proof. A separate read-only cart probe on the same fresh profile saw no cart item evidence. ThriftBooks is a hard-site/non-durable-cart finding, not proof.
- No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Checks:
- Focused Ace and ThriftBooks search/product/cart URL, cart proof, filter-control rejection, and base-book-over-workbook selection checks passed.
- `engine/.venv/bin/python -m py_compile engine/anticipy_engine/agent/webvoyager.py` passed.
- `PYTHONPATH=engine engine/scripts/test_browser_hand.py` passed.
- `PYTHONPATH=engine engine/scripts/test_handoff.py` passed.
- `PYTHONPATH=engine engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Forbidden-path, secret-shaped diff, and product/eval literal scans passed.
- Ports `8787`, `7777`, and `9222` are clear.

Gate:
- No all-work human gate is active.
- Separate judge quota blocks proof only, not building.
- Ace and ThriftBooks both produced real-chain hard-site/non-durable-cart findings. The selection hardening is kept because it prevents a real wrong-product mutation path.

Proof status:
- M3 is not done.
- This lap is real-site support, real-chain failure hardening, and hard-site discovery. It is `UNPROVEN-PENDING-JUDGE`.
- Generalization remains UNPROVEN.

Next:
- Continue M3 ladder work only. Convert unjudged successful cart artifacts through the separate judge when quota returns. Until then, keep building memory-to-intent, real-site DOM recipes, cheap planning, sideways real-store paths, and failure hardening.
