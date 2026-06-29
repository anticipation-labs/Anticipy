# PROGRESS JOURNAL (newest first)

Format: each entry = date · what I did · proof · next. This is my resume point after any reset.

## 2026-06-28 — BROWSER Y0 Step 2: rip ALL hardcoding + gate refusals behind one flag
- `agent/webvoyager.py` (2709 → 767 lines): deleted `_try_amazon_return_recipe`, `_try_commerce_recipe`,
  and ~40 commerce/Amazon-specific helpers. The agent now runs ONE general observe→plan→act→verify loop
  on every site. Added `ANTICIPY_BROWSER_UNLOCKED` (default ON): the brain decides + the hands act
  (click buy, place orders, type any field). Set =0 to re-arm the purchase/credential/checkout
  guardrails (safety/demo mode). SSRF/private-IP guard is SEPARATE and ALWAYS on (test_navwall green).
- `core/control_core.py` (4437 lines): `_web_start_url` is now fully horizontal — explicit URL → bare
  domain → Google search; ZERO keyword→site map, ZERO owner-TLD baking. Proof: "return … on amazon"
  → google search (not amazon.ca). Deleted the entire demo-Amazon subsystem (`_demo_amazon_return_*`,
  `_rearm_demo_amazon_return_record`, `_is_*_demo_amazon_*`) and its `main.py` lifespan fixture.
- Removed the now-dead `site_hints` module (a host→behaviour lookup table) + its wiring + test; no
  runtime consumer remained after the recipes were ripped. (`site_hints_seed.json` kept — storesite uses it.)
- TESTS: repurposed `test_browser_safety_loop` + `test_purchase_guard` to pin the NEW flag-gated
  contract (UNLOCKED dispatches a purchase click; LOCKED stops it; SSRF always on) instead of the old
  always-on refusal; trimmed the deleted-recipe + demo-amazon cases from `test_browser_result_on_card`.
- PROOF: full `scripts/run_suite.sh` → 100 passed, 12 failed; ALL 12 failures are PRE-EXISTING (fail
  identically on clean HEAD 936220b — they are prior-session frontend/owner-flow gaps, untouched by this
  rip). Every browser test green: purchase_guard, browser_safety_loop, browser_prompt_injection, navwall,
  form_prepare, browser_hand, agent_proof, browser_use_cdp, browser_result_on_card, handoff, storesite.
- NEXT: Step 3 — DOM/accessibility-tree-first perception (primary input), set-of-marks screenshot as
  fallback; instrument $/task + which model per step.

## 2026-06-28 — Phase 1 kickoff
- Pulled `~/Anticipy` (factory/build) into the VM, branch `devin/full-frontend-ui`. Cleaned macOS
  AppleDouble junk that broke the git index. Git healthy. 102G free.
- Set up engine venv (slim cloud reqs, no whisper). Engine boots: `GET /health` → 200 OK on
  `127.0.0.1:8787`, serving `web/` via StaticFiles.
- Wrote `docs/build/MASTER_PLAN.md` (8-phase roadmap, my context anchor) and
  `docs/build/PHASE_1_FRONTEND_UI.md` (the 15-page plan, reuse map, coming-soon strategy).
- Design system extracted from existing UI: cream #FBF9F4 / #F5F1E8, ink #171615, gold #B8924A;
  DM Serif Display + Inter; film-grain; "ANTICIPY — Vibe your life"; anticipy.ai.
- NEXT: build shared `web/anticipy.css` + `web/anticipy.js` (tokens, session boot, coming-soon
  helper, toast), then Welcome + Sign with Supabase, then the onboarding flow.
