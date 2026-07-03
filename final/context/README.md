# final/context — the ONE final context / memory system  [STATUS: LEARNS-YOU DONE (Phase 3)]

The "context engineering" layer. What lets the brain **resolve the right reference** when you say
"grab my usual" or "email Sam," and **learn you** over time so it never re-asks a fact it was told.

## What works today (Phase 3 — the learns-you package, no keys)
`ContextEngine` (`engine.py`) sits behind the live_memory facade and wires into intake at two seams
(`control_core._owner_ingest_inner`): `observe()` runs before the brain; `resolve_observed()` runs
after the transcript-scoped intent resolve. It ships the four learns-you deliverables:

- **(a) memory-anchored reference resolution** (`reference_resolver.py`, grafted from DEV-FINAL
  `app/anticipy/memory.py:260`): "grab my usual coffee" → the stored *large oat milk latte*.
- **(b) Mem0-style ADD/UPDATE/DELETE/NOOP reconcile** (`reconcile.py`, grafted from
  `memory.py:185`) incl. explicit retraction: "never mind the bank thing" **DELETEs** the matching
  open loop instead of leaving it lingering.
- **(c) per-person dossier** (`dossier.py`, grafted from `product/dossier_active_loader.py`:
  `Person`/`pronoun_map`/`do_not_touch`): two Sams → resolve the one, or **ask which**.
- **(d) never-re-ask ledger** (`never_re_ask.py`): before the brain asks for a slot, it checks
  memory for a known value and fills it instead of asking.

Facts the wearer states ("Sam Rivera is my lawyer", "I'm allergic to penicillin") are captured into
the profile drawer by `observe()` — the proactive pipeline drops pure facts as "ignore", so without
this they'd be lost. Everything is fail-safe: a memory hiccup no-ops, an empty context leaves the
line byte-identical, and per-user isolation + right-to-delete are inherited from the drawers.

## Proof
`final/tests/context_eval.py`: **3/8 → 7/8** (resolve 'my usual', disambiguate two Sams, surface a
known allergy, handle a retraction, + the two never-re-ask cases). Case 7 (standing preferences)
is the remaining gap. No regression: `proactive_eval.py` 14/15; `run_suite.sh` fail-set unchanged.

## Still open (future phases, per cozy-chasing-comet.md)
- **Style learning** — nothing yet learns *how you write* (needs real sent-message history).
- **Standing preferences** — "morning only / never before 9am" not yet applied to scheduling.
- **Semantic retrieval** — real embeddings + ANN + a temporal knowledge graph (Phases 1 & 4).
