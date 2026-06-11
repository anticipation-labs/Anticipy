# Last lap: 20260611T135937Z (groundwork — site_hints extraction, TARGET v8 STAGE B item 1)

## What changed
- NEW engine/anticipy_engine/agent/site_hints.py: SiteHints store — packaged JSON seed +
  per-engine learned overlay (<data>/site_hints.json), exact-then-longest-suffix host
  matching, per-field overlay-wins merge, verified-fact learn() with atomic write,
  corrupt-overlay .corrupt set-aside, invalid fields dropped toward seed, no-path-no-IO.
- NEW engine/anticipy_engine/data/site_hints_seed.json: one-time export of webvoyager's
  three host tables (35 hosts), generated programmatically from the live module BEFORE
  deletion and read back equal. Placed OUTSIDE agent/ because factory scan 5 greps added
  quoted hostnames under the whole agent/ subtree (ledger D24).
- engine/anticipy_engine/agent/webvoyager.py: the three dicts DELETED; the three helpers
  delegate to the store (all ~23 internal call sites untouched); learn write-back at the
  two durable cart-proof chokepoints via _learn_from_durable_proof (verbatim facts only,
  never raises, mock-unreachable).
- engine/anticipy_engine/core/control_core.py: site_hints.configure(<data>/site_hints.json)
  (the pending_path wiring precedent; agent code never reads env).
- engine/scripts/test_site_hints.py (suite 45->46): seed parity vs the embedded old tables,
  helper parity (incl. macys lookahead + containerstore host-pattern authority), overlay
  learn/merge/durability, learn bounds (seed-equal facts refused, off-host/no-{q}/bad-regex
  refused, examples dedupe+cap), corrupt set-aside, no-path-no-IO, ControlCore wiring,
  mock-never-learns, proof-seam sanitization.

## Eval numbers seen (stub, dev bank)
- Suite 46/46 GREEN.
- Owner lane (OFFICIAL, ANTICIPY_OWNER_INGEST=1) pre AND post: catch 1.0/1.0, false 0,
  harm 0, interrupt 0.625/1.0, e2e 0.6483, correct 0.8475, recall 1.0 — bit-identical
  (aggregate AND per-persona). Default lane identical too.
- Per-line decision diff ZERO (493 lines x 16 persona-days per lane); normalized
  full-response diff ZERO; goal (intent,state) multisets identical; no site_hints
  artifacts in any run dir. Disclosed instrument-dead by design (F31 ceiling).

## What's next
- P4 build lap: generalize the no-hints path over the hints store; fix F32 (let VERIFIED
  learned cart paths extend cart-URL recognition under the same verified-only law).
- Foreman: gate_P4.sh does not exist yet; bank v2 (F31); OWNER_PHONE confirm for Stage A.
- STAGE B item 2 remains: agent/proof.py — generalize the multi-read read-back discipline
  beyond carts.
