# Last Lap

Lap: 20260611T105558Z (build, TARGET v7 item 1 — e2e_completion_rate, ledger F29)

## What changed
- `engine/anticipy_engine/shared/storesite.py` (NEW) — store-name -> site
  derivation: a PRODUCT-shaped memory line's single-word capitalized store name
  after at/on/from becomes `https://www.<store>.com`. No retailer literals, open
  vocabulary, every deny bound fails toward "": multi-word proper nouns
  ("Lincoln Elementary", "Best Buy", "Hoka Bondi 9") refuse structurally,
  possessives ("at Bob's") refuse, weekday/month/holiday/generic-place closed
  class refuses, non-product lines refuse; mixed-case brands (eBay, IKEA) miss
  by design (disclosed residual).
- `engine/anticipy_engine/proactive/harm.py` — the existing memory-resolved
  vague-cart ACT rule now actually fires on real speech: `_VAGUE_CART` accepts
  bounded modifiers between determiner and head ("that water table thing",
  "the clamp one"); `_MEM_PRODUCT` re-aligned with the orchestrator's
  product-hint verbs (the "comparing" drift); `_memory_has_cart_target` accepts
  a derived store site as a real site. Money rule still first and untouched.
- `engine/anticipy_engine/core/orchestrator.py` — `_line_site` falls back to
  the same derivation; `_BROWSER_ACTION_RE`/`_VAGUE_BROWSER_RE` anaphors get the
  same bounded modifier tolerance; `memory_resolution` records
  `site_derived_from_store_name` honestly.
- Deliberately NOT done (F29 near-miss, ledgered): widening bare spoken cart
  verbs ("stick/throw it in the cart") — a storeless flipped line (teacher_rob)
  would junk-complete through the stub planner's canned "later"->write_memory
  step. Storeless cart-put lines stay fail-safe asks, pinned.
- Pins: `test_storesite.py` (NEW, 19-case accept/deny battery, in run_suite.sh);
  F29 CART_CTX battery + 3 no-ctx deny pins in `test_harmline.py`;
  `test_memory_resolved_store_name_plan` in `test_orchestrator.py` (derived-site
  step with provenance, storeless plans NOTHING, goal done with proof, zero
  model calls). All pin sentences are non-bank.

## Numbers I saw (builder-side, stub, dev bank)
- OFFICIAL owner lane (ANTICIPY_OWNER_INGEST=1): e2e_completion_rate
  0.5918 -> 0.6305 (+0.0387 — past the 0.02 epsilon; exactly the two intended
  completions). catch 1.0/1.0, false 0, harm 0, interrupt 0.6875/1.5,
  recall_worst 1.0 EXACTLY unchanged. correct_action_rate 0.7909 -> 0.8296.
- Default lane: e2e equally 0.6305 (shared harm/plan plumbing, disclosed);
  interrupt 0.625/1.0 and all other aggregates at ratchet bests.
- Per-line decision diff pre->post, BOTH lanes, 493 lines x 16 persona-days:
  EXACTLY 2 flips (parent_dana d01 L38 water table, student_kayla d01 L27 desk
  lamp; ask->act), zero others. Goal-state diff: exactly those two goals
  waiting->done, labeled mock proof + derived-site provenance
  (target.com / amazon.com from "at Target" / "on Amazon" memories).
- Suite 43/43 (42 + new storesite). Scorer selftest PASS. Zero spend, zero
  real-world artifacts.

## Exactly which items moved (2 completions, 2 personas)
- parent_dana d01 "grab that water table thing ... stick it in the cart"
  (memory: Step2 water table at Target -> https://www.target.com)
- student_kayla d01 "grab that desk lamp from my cart, the clamp one"
  (memory: blue light desk lamp on Amazon -> https://www.amazon.com)

## What's next
1. dana d02 "Book the Friday 9am one" (expected act, still asks): anaphoric
   slot-choice booking rule — same-line appointment-noun anchor (checkup/
   appointment/cleaning/visit), closed-class travel/purchase-noun deny ("book
   the 9am flight" must stay money-gated) + a grounded stub create_event plan.
   Worth pairing with F27's "block X to Y" calendar trigger (same plan-layer
   slice). Each is ~+0.018 aggregate e2e alone — pair them to clear epsilon.
2. luis DeWalt / amara Hoka / rob IPEVO cart items: NO store in memory — honest
   fail-safe; needs richer owner-path shopping-context capture, not a wider
   derivation. pri's "buy" stays behind the F23 money stance (foreman queue).
3. The 16 expected-asks are the e2e structural ceiling (scorer counts
   completions only on expected acts); per-persona ceiling avg ~0.78.
4. P3 live gate still waits ONLY on OWNER_PHONE confirmation (PENDING_FOR_OMAR);
   gate_P3.sh does not exist yet (foreman item).
