# Last Lap

Lap: 20260609T140258Z
Date: 2026-06-09T14:25:29Z
Milestone: M3 - exact Target product selection and CDP profile-dir hardening
ALL_MILESTONES_DONE: false

Judge verdict: UNPROVEN-PENDING-JUDGE, Tamper: NOT_RUN

What changed:
- WebVoyager now scores compact ordered item-token sequences, so an exact product title such as `OXO Dish Brush` outranks broader titles where the requested tokens are scattered.
- Product selection no longer rewards longer titles when token hits tie.
- Navigated observations with URL/title but no text or actionable elements are treated as not ready, and empty search surfaces are re-observed or scrolled before the commerce recipe fails.
- `NativeBridgeLink` now creates the configured Chrome user-data directory before CDP launch, so fresh per-lap profiles can actually start Chrome and return actionable marks.

Real runs:
- A Target run with a missing sub-brand in the remembered item failed safely without an Add click.
- A pre-fix Target run selected a broader soap-dispensing palm brush product and verified broad cart text. This is counted as a false action, not progress.
- A post-ranking rerun still failed safely because CDP Chrome did not start when the fresh profile directory did not exist, leaving the bridge with zero actionable Target marks.
- After profile-dir creation, a sanitized direct Target probe saw 299 actionable elements and 131 product-like Target links.
- The final live `/event` run seeded context-only memory, then sent a vague action that did not name the site or exact item. The hand resolved Target plus `OXO Dish Brush`, opened the exact `/p/oxo-dish-brush/-/A-80221510` product, clicked a real Add to cart control, opened Target cart, and durable cart read-back matched the item.
- No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Checks:
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
- Ports `8787`, `7777`, and `9222` were cleared after live runs.

Gate:
- No all-work human gate is active.
- Separate judge quota blocks proof only, not building.
- Latest work remains `UNPROVEN-PENDING-JUDGE`.

Proof status:
- M3 is not done.
- Generalization remains UNPROVEN.

Next:
- Continue M3 ladder work on real stores only. Convert the unjudged Target exact-item cart path through the separate judge when quota returns, and otherwise keep building exact item matching, durable read-back, and cheap real-site action recipes.
