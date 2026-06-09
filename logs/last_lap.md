# Last Lap

Lap: 20260609T131645Z
Date: 2026-06-09T13:39:42Z
Milestone: M3 - active-page cart proof and exact token-rich product matching
ALL_MILESTONES_DONE: false

Judge verdict: UNPROVEN-PENDING-JUDGE, Tamper: NOT_RUN

What changed:
- Active-page cart completions now require independent `fresh_probe` confirmation before WebVoyager can mark commerce success. This applies after search-result add, product-page add, refresh, scroll, and View Cart flows.
- Known-cart and fresh-probe cart observations now scroll cart pages and keep the highest-signal cart state before deciding whether item evidence is present.
- Product matching for token-rich remembered items now keeps leading distinctive tokens and requires roughly 80 percent token overlap for item names with five or more tokens.
- Query fallback for token-rich items now uses the full required token threshold instead of accepting broad product rows.
- Added a lesson that brand plus category is not enough when a remembered item includes material or feature modifiers.

Real runs:
- A live Lowe's vague-memory run resolved a yard request from memory to Lowe's plus a token-rich gloves item, clicked a real Add to Cart control, opened the cart, and failed final cart verification because the cart evidence did not match the remembered item.
- A rerun after distinctive-token hardening selected the exact brand-bearing product URL, clicked Add to Cart, opened the cart, and still failed final proof because cart read-back saw only count/header structure with no exact item evidence.
- After cart-scroll proof hardening, another rerun selected a broader brand/category product, clicked Add to Cart, and was rejected by strict cart evidence.
- After stricter token-rich matching, the final rerun still reached a brand-bearing product URL and clicked Add to Cart, but final cart proof rejected the item because the visible cart evidence did not match the full remembered item.
- A read-only cart probe scrolled the real Lowe's cart through 12 observations; cart count stayed nonzero, global token hits stayed partial, and cart item windows stayed at zero.
- These live runs are failures and include wrong or unverified cart additions. They are not progress proof. No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Checks:
- `engine/.venv/bin/python -m py_compile engine/anticipy_engine/agent/webvoyager.py engine/anticipy_engine/core/orchestrator.py engine/anticipy_engine/core/native_bridge_link.py engine/anticipy_engine/hands/browser_hand.py` passed.
- Focused active-page fresh-probe cart completion checks passed.
- Focused cart-scroll proof checks passed.
- Focused token-rich product matching checks passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_hand.py` passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_handoff.py` passed.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Forbidden-path scan was clean.
- Secret-shaped diff scan was clean.
- Product diff eval-literal scan was clean.
- Ports `8787`, `7777`, and `9222` were cleared after live runs.

Gate:
- No all-work human gate is active.
- The Lowe's token-rich gloves path is a hard-site or exactness finding, not a stop. Other M3 stores and rungs remain available.
- Separate judge quota still blocks proof only, not building. Spending money remains a human gate and was not taken.

Proof status:
- This lap is `UNPROVEN-PENDING-JUDGE`. The separate judge has not verified any M3 artifact.
- M3 is not done.
- Generalization remains UNPROVEN.

Next:
- Continue M3 ladder work on real stores only. Prefer exact item matching and independent read-back proof. Do not retry the Lowe's token-rich gloves path blindly without a new exact-product or cart-readback hypothesis.
