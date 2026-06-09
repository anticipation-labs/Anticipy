# Last Lap

Lap: 20260609T211215Z
Date: 2026-06-09T21:26:21Z
Milestone: M3 - Vitamin Shoppe DOM-order adjacent Add hardening
ALL_MILESTONES_DONE: false

Judge verdict: UNPROVEN-PENDING-JUDGE, Tamper: NOT_RUN

What changed:
- `NativeBridgeLink` now preserves direct-CDP document order as `docIndex` when normalizing set-of-mark elements.
- Direct-CDP capture now emits `docIndex` alongside ranked `idx`, so useful product/Add controls can stay priority-ranked without losing true page order.
- WebVoyager now knows Vitamin Shoppe search, product, and cart URL shapes: `/search?search=...`, `/p/<slug>/<sku>`, and `/cart/shopping-cart`.
- Search-result adjacent Add selection, nearby-product lookup, and generic Add unrelated-product guards now use document order when available, instead of ranked `idx` order.

Real runs:
- A read-only Vitamin Shoppe probe with an over-exact apostrophe query returned a near-empty search shell, so the lap moved to the viable real query shape instead of forcing a dead surface.
- A read-only Vitamin Shoppe probe for a vitamin-D item exposed 475 actionable elements, `docIndex` on normalized elements, buyable `/p/...` product links, real `Add to Cart` buttons, and the mapped cart route. The matched product had ranked `idx=4` and document order `docIndex=81`; the adjacent Add button had ranked `idx=0` and document order `docIndex=87`, confirming the ranked-index bug.
- A fresh live `/event` run used context-only memory plus a vague action that named neither Vitamin Shoppe nor the item. The chain resolved the remembered supplement item and site from memory, opened the real Vitamin Shoppe search page, clicked the real adjacent `Add to Cart` button, and then failed closed because the mapped cart route exposed no durable item evidence.
- Direct read-only native-bridge read-back after the live run saw the active page and cart route at `/cart/shopping-cart`, but both exposed no item evidence or actionable cart controls. Vitamin Shoppe is a hard-site/non-durable-cart finding, not proof.
- No checkout, payment, order placement, email, calendar change, or third-party message occurred.

Checks:
- Focused Vitamin Shoppe URL-shape and document-order adjacent-Add checks passed.
- `engine/.venv/bin/python -m py_compile engine/anticipy_engine/agent/webvoyager.py engine/anticipy_engine/core/native_bridge_link.py` passed.
- `PYTHONPATH=engine engine/scripts/test_browser_hand.py` passed.
- `PYTHONPATH=engine engine/scripts/test_handoff.py` passed.
- `PYTHONPATH=engine engine/scripts/test_harmline.py` passed.
- `bash scripts/run_suite.sh` passed 29/29 in stub/mock mode. This is regression coverage only and does not prove M3.
- `git diff --check` passed.
- Forbidden-path, credential-shaped diff, and product/eval literal scans passed.
- `logs/trace/20260609T211215Z.jsonl` is ignored.
- Ports `8787`, `7777`, and `9222` are clear.

Gate:
- No all-work human gate is active.
- Separate judge quota blocks proof only, not building.
- Vitamin Shoppe produced a real Add-click mutation path but no durable cart artifact under read-back. The document-order hardening is kept because it prevents adjacent Add controls from being missed or mis-paired when observation ranking changes `idx` order.

Proof status:
- M3 is not done.
- This lap is real-site DOM recipe hardening and hard-site discovery. It is `UNPROVEN-PENDING-JUDGE`.
- Generalization remains UNPROVEN.

Next:
- Continue M3 ladder work only. Convert unjudged successful cart artifacts through the separate judge when quota returns. Until then, keep building memory-to-intent, real-site DOM recipes, cheap planning, sideways real-store paths, and failure hardening.
