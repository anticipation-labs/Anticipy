# FAILURES — failure modes + tripwires (do not repeat)

The immune system. Never erase. Each entry: what broke, why, and the tripwire that catches a relapse.
Deep history: `logs/factory/FAILURES.md` + `logs/factory/FAILURE_MODES.md` + `FOREMAN_STATE.md`.

### F-001 — "Model is blocked/unfunded" assumed without a live test
- **Cause:** hours burned insisting the runtime model was rate-limited/unfunded; never ran a live call.
  It was funded and fast (~½s) the whole time.
- **Tripwire:** before claiming blocked/broken/done, run a check that can FAIL (Constitution rule:
  verify, never assume). Re-verify the model route every session (RESEARCH_LEDGER lane 1).

### F-002 — Sarcasm/vent rode a verb into an autonomous ACT (the cardinal sin)
- **Cause:** decider over-weighted "I'll/I owe/I promised" shapes; a vent clause produced an act/ask.
- **Tripwire:** `safety_mega_eval` must stay BREACHES 0, run independently through the real
  `/owner/ingest` split path with `execute_actions=True`. Any card/act from a vent = breach = revert.

### F-003 — Multi-task decomposition severed the action clause from its vent frame
- **Cause:** splitting a compound line ran "book the room" in isolation, losing the vent marker in a
  sibling clause → a vent produced an act. Builder + tester reported "BREACHES: 0" — a FALSE NEGATIVE
  (the eval was blind to the ingest split path at the time).
- **Tripwire:** a vent marker in ANY clause must suppress/ask-gate the WHOLE breath; never re-evaluate
  clauses independently without carrying line-level emotional context. The hardened floor now covers
  the ingest path. Multi-task decomposition is still WANTED but only with whole-breath vent propagation.

### F-004 — Self-attestation / write-response treated as proof
- **Cause:** trusting a builder's report or a write API's 200 as "done."
- **Tripwire:** no-slop law — independent skeptic + independent read-back of the real artifact. A test
  the builder could have edited proves nothing.

### F-005 — Stale-base worktree patches merged blindly
- **Cause:** integrating a patch built against an old HEAD.
- **Tripwire:** integrator re-applies verified patches to current HEAD and re-runs receipts; stale-base
  patches are design input, not landable code.

### F-006 — Live Twilio spammed Omar (the 31-text history)
- **Cause:** autonomous live-channel sends while Omar was away.
- **Tripwire:** unattended default = channels=mock, `ANTICIPY_INBOUND_POLL_SECONDS=0`, mic OFF. Live
  call/SMS only to Omar's confirmed number, only when supervised/approved. (Engine is currently
  channels=live — see CURRENT_TRUTH watch-item; do not send.)

### F-007 — Message cap shipped as anti-spam (BANNED)
- **Cause:** added a per-day message cap ("NF8") to stop spam. Omar banned caps/throttles.
- **Tripwire:** the brain is the anti-spam. If it spams, fix the inference, never the mouth.

### F-008 — Render-layer scrub mistaken for an engine cure
- **Cause:** premium reskin humanized/deduped card copy at the UI layer; the engine still emits
  rule-name titles, route-tag reasons, `[Anticipy test]` labels, and over-generates asks from one vent.
- **Tripwire:** distinguish "machinery exists / mock integrated" from "live proven." The durable fix is
  engine-side (cadence + over-asking, PRD NF8–NF12/F8–F11).

### F-009 — Loop-for-looping / research taper / grinding a saturated metric
- **Cause:** spawning audit waves on already-green code; broad research with no decision; grinding a
  metric stuck at ceiling.
- **Tripwire:** every cycle moves a real gate or it didn't count. 3 cycles with no receipt → halt + re-aim.
  Research must end in a decision (RESEARCH_LEDGER), not a dump.

### F-012 — Duplicate over-extraction: one real task surfaced as 2–3 cards (spam) [RESOLVED 2026-06-16]
- **Resolution:** engine-side semantic consolidation after moat expansion
  (`control_core._consolidate_obligations` + `_obligation_sig`): drop filler/pronouns/time/generic
  verbs, key on the object-noun signature, merge when one obligation's signature contains the other.
  "Mom: call Amazon about the plant" + "Yeah, I'll handle it" (→ "handle the Amazon plant order") +
  reworded variants collapse to ONE; distinct objects never merge; the vent guard (force_ask)
  propagates on merge (safety only gets stricter). Proven through the REAL app UI (R-2026-06-16-D):
  8-line transcript → 4 cards (Amazon/Sam/pickup/CRM), both vents silent, money parked, NO duplicates.
  `test_owner_duplicate_collapse` (deterministic); suite GREEN 91/0; `safety_mega_eval` 0 breaches.
- **Known limitation (open):** consolidation is WITHIN one ingest. Cross-ingest live re-submit can still
  reword (model nondeterminism) → `_existing_owner_card` is exact-text, so a reworded re-submit could
  add a near-dup. Stub re-ingest is idempotent (public_backend_path replay). A semantic
  `_existing_owner_card` is the durable follow-up.

### (original) F-012 detail
- **Found 2026-06-16** driving Omar's test transcript through the real app UI. The same underlying task
  produced multiple cards: Amazon plant → "call Amazon about the plant I ordered" + "call Amazon about
  that plant" + "Confirm task: handle the Amazon plant order" (×3); Sam deck → "Clarify possible request"
  + "get Sam the deck by Friday" (×2); pickup → "Ready" card + "Confirm task: pickup moved to 3 today" (×2).
- **Cause (hypothesis, to verify):** the moat (`proactive/extract.py` + `_spine_card`) extracts a task
  per line AND from confirmations ("Yeah, I'll handle it" → its own task) AND emits a separate
  "Confirm task:" variant — with no semantic dedup/consolidation across a breath. So a 2-line exchange
  about ONE action becomes 3 cards.
- **Why it matters:** this is exactly the spam Omar bans ("the brain is the anti-spam, not a cap"). It is
  NOT a safety breach (all asks/parked, vents silent, money parked) but it makes the product feel dumb.
- **Tripwire (to build):** an eval transcript where one action is stated + confirmed across ≥2 lines must
  yield exactly ONE card. Dedup must be semantic (same action/target), not just exact-text.
- **Also found:** the running :8787 engine was a STALE process (old code) 500ing on execute=true; always
  verify the LIVE engine serves the committed code (restart on a clean checkout when in doubt). Fixed.

### F-011 — Browser round-trip refactor (b82e660) regressed the suite + introduced spam-adjacent defects
- **Found 2026-06-16** by re-running the suite (it was RED 86/4, not the imported "90/90 GREEN" — verify,
  never trust). The "confirm-first browser round-trip" (Omar's centerpiece, `control_core.py`) landed
  without updating 3 tests AND introduced real defects:
  1. **Duplicate ask:** a no-memory cart line registered a cart-prep ask (category `browser`) AND the
     unified round-trip gate fired a second `browser_action` ask — one web task → two pending asks.
  2. **Non-idempotent re-ingest:** the browser ask used a random `new_id()`, so replaying the same
     transcript spawned new browser asks + a stray saved goal each time (pending/goals grew).
  3. **Capability dropped:** the prior memory-grounded auto-cart (resolve store+item → auto-execute to
     e.g. staples.com with a `browser_receipt`, ask only when unsure) was replaced by uniform
     confirm-first. This is more conservative/safer but loses "prepare generously" auto-prep and
     over-catches some context lines (e.g. a Lowe's "was comparing…" line) as browser asks.
- **Resolution — Omar chose "prepare when confident" (2026-06-16):** restored the Donna magic + kept the
  safe round-trip. Final engine state (`control_core.py`, `owner_mode.py`):
  1. **Resolved cart auto-prepares:** when memory/onboarding resolves the exact item+store, the cart
     auto-executes (browse_task in a THROWAWAY browser, money/checkout guard → never buys) with a
     `memory_resolution` receipt. `_spine_card` checks `_has_external_context`; resolved → `args.resolved_cart`
     → the round-trip gate skips it; unresolved → `_browser_action_ask`.
  2. **Unresolved → confirm-first round-trip:** ONE deterministic ask id (`br_<sha256(source|task)>`),
     so re-ingest reuses the same pending entry (idempotent — no duplicate ask, no stray goal).
  3. **Context-line over-catch fixed at the root:** `_BROWSER` matched the noun "grab" in "grab **bars**"
     (a bathroom rail) → a descriptive line shaped as a browser task. Added a negative lookahead
     (`grab(?!\s+bars?\b)`) — keeps the verb, drops the product-noun. lowes_context now ignores like its siblings.
  4. **Decline/approve write-back:** declining a browser ask now marks its durable card `declined`
     (was stranded `open`); YES marks `running`. `_resolve_browser_card_record`.
- **Verification:** suite GREEN 90/0; `safety_mega_eval` BREACHES 0 (independently re-run); the 4
  originally-red tests (owner_ingest_event, public_backend_path, messy_proactive_handoff,
  owner_app_product_path) all pass against the real behavior.
- **Tripwire:** suite must be GREEN and re-run (not trusted) every session; one web task = one pending
  ask; re-ingesting an identical transcript must not grow pending/goals; resolved carts auto-prepare,
  unresolved ask.

### F-010 — Verifying the moat on the wrong path (preview vs reality)
- **Cause:** stress-testing with `execute=false` (preview) showed dropped tasks; the real app path uses
  `execute=true` and caught them. Wasted a cycle on a false alarm.
- **Tripwire:** verify the moat with `execute=true` (the real path the app uses), not preview.
