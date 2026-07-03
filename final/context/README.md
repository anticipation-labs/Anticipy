# final/context — the ONE final context / memory system  [STATUS: LEARNS-YOU DONE (Phase 3) + STANDING PREFERENCES]

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

- **(e) standing preferences** (`engine.py` `_preference_from`/`_scheduling_prefs`): "I only take
  meetings in the morning" / "never book me anything before 9am" — statements the pipeline would
  drop as an ignored open loop — are captured as a DURABLE `preference` profile fact, then echoed
  onto a scheduling/booking card ("set up a call with Dana") so the constraint is honored instead
  of ignored. Narrow patterns (only/never/prefer/no-meetings/always-take) disjoint from the "usual"
  anchor set; echo is double-gated (a scheduling line AND a stored scheduling preference), so it
  never annotates an unrelated task.

## Proof
`final/tests/context_eval.py`: **3/8 → 8/8** (resolve 'my usual', disambiguate two Sams, surface a
known allergy, handle a retraction, apply a standing preference, + the two never-re-ask cases). No
regression: `proactive_eval.py` 13–14/15 (model-noisy band); `run_suite.sh` 113/9 fail-set
byte-identical to baseline.

## Phase 1 — real Gemini embeddings (paraphrase-robust recall) [behind a flag]
`memory/embed.py` now has a THIRD embedder: real Gemini cloud embeddings
(`gemini-embedding-001`, 768-d) via `GOOGLE_API_KEY`, behind `ANTICIPY_EMBED_PROVIDER=gemini`.
Default stays on-device (stub / bge), so the free suite + the working 8/8 are untouched. Results
are L2-normalized + in-process cached; rate limits / 5xx retried with backoff; a missing key or
exhausted retries falls back to on-device (never crashes ingest). `embed_batch()` uses the
`batchEmbedContents` endpoint. Swapping providers on an existing store needs `Memory.reindex()`.

- **Proof** (`final/tests/embed_gemini_proof.py`): store "schedule a trim" beside a keyword trap
  ("book a table"), then query "book a haircut" (zero content-word overlap). STUB is fooled — it
  ranks the trap #1 and the true memory only 0.33; GEMINI recalls "schedule a trim" #1 at **0.926**.
- **No regression** (flag ON, throwaway :8791 engine, live Gemini — stored vectors verified 768-d):
  `context_eval` **8/8**, `proactive_eval` 14/15 (in-band), suite fail-set unchanged.

## Still open (future phases, per cozy-chasing-comet.md)
- **Style learning** — nothing yet learns *how you write* (needs real sent-message history).
- **ANN + temporal graph** — retrieval is still O(n) cosine; a Neo4j temporal knowledge graph is Phase 4.
