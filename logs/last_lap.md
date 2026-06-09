# Last Lap

Lap: 20260609T183424Z
Date: 2026-06-09T18:58:37Z
Milestone: M3 - Ulta real-store recipe and cart durability hardening
ALL_MILESTONES_DONE: false

Judge verdict: UNPROVEN-PENDING-JUDGE, Tamper: NOT_RUN

What changed:
- WebVoyager now knows Ulta search, product, and bag URL shapes.
- Product-page add matching now recognizes real shipment labels such as `Add for ship`.
- Generic `Add to bag` buttons are rejected when nearby product-card context points at an unrelated recommendation product.
- Cart proof now requires five independent fresh cart reads spaced five seconds apart. If any delayed read misses the item, the helper returns that failing observation so callers cannot complete from an earlier best state.

Real runs:
- Read-only Ulta probing found a real search page with exact product links, `Add to bag` controls, and `/bag`.
- A first live vague-memory run resolved the site and item correctly, opened the exact Ulta product page, missed the main `Add for ship` control, clicked a lower-page recommendation `Add to bag`, and correctly failed final cart proof.
- After add-control hardening, short-window cart reads could still flicker true and later false. Those runs are not proof.
- After five-read durability hardening, the final fresh live `/event` run again resolved the vague task to Ulta and the target cleanser, but failed closed under final cart proof instead of claiming a transient bag state.
- No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Checks:
- `engine/.venv/bin/python -m py_compile engine/anticipy_engine/agent/webvoyager.py engine/anticipy_engine/core/native_bridge_link.py engine/anticipy_engine/core/orchestrator.py engine/anticipy_engine/hands/browser_hand.py` passed.
- Focused Ulta URL, add-label, unrelated-recommendation, and exact-card guards passed.
- Focused cart durability helper check passed.
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
- Ulta is a current hard-site finding until a future hypothesis produces a cart artifact that remains durable past the stricter proof window.

Proof status:
- M3 is not done.
- This lap is failure hardening and real-site support only. It is `UNPROVEN-PENDING-JUDGE`.
- Generalization remains UNPROVEN.

Next:
- Continue M3 ladder work only. Prefer another real store or a concrete Ulta durability hypothesis over blind Ulta retries. Convert prior unjudged cart artifacts through the separate judge when quota returns.
