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

## Phase 4 — the Neo4j temporal knowledge graph [behind a flag]
`graph.py` is a focused, custom entity/relationship graph on the live Neo4j (AuraDB Free),
behind `ANTICIPY_GRAPH=neo4j`. Default OFF → `ContextEngine.graph is None`, no network is
touched, and intake is byte-identical to Phase 3. (Chose a custom graph over graphiti-core:
graphiti pulls a heavy async LLM stack whose Gemini path is finicky to verify in a night; the
disambiguation + multi-hop we need is a small, provable graph.)

- **Model.** Nodes `(:Owner {scope})` and `(:Entity {name, scope, kind})`; edges
  `(A)-[:REL {predicate, valid_from, valid_to, ingested_at, invalid, statement}]->(B)` read
  "A's `predicate` is B". **Bi-temporal:** `valid_from`/`valid_to` are VALID-time, `ingested_at`
  is TRANSACTION-time. A contradicting fact for a *functional* predicate (one holder:
  accountant/employer/…) doesn't overwrite history — it sets `invalid=true`+`valid_to` on the
  prior edge (soft-delete), so "who was my accountant before Bob?" stays answerable.
- **Wiring.** `ContextEngine` mirrors captured people into the graph on `observe()` (owner
  relations from "X is my role", person-to-person from "Jane is Mia's assistant"), and consults
  it in `resolve_observed()`: an ambiguous first name is resolved by **relationship context**
  (a "signed contract" points at the lawyer Sam, not the brother Sam) instead of always asking,
  and a possessive chain ("email **my accountant's assistant** the receipt") is answered by a
  **multi-hop traversal** `Owner-[accountant]->Mia-[assistant]->Jane`. Every call is fail-safe:
  a missing key / unreachable DB / Cypher error logs and no-ops, reads return empty.
- **Proof** (`final/tests/graph_proof.py`, live Neo4j, isolated scope, self-cleaning): two Sams
  with different relationships → traversal disambiguates the lawyer from the brother (and stays
  ambiguous with no cue); `who is my accountant's assistant?` → Jane via Mia; the accountant
  changes Mia→Bob → the Mia edge goes `invalid=true`/`valid_to` set (history kept) and the
  multi-hop correctly returns empty. Also proven end-to-end through the ContextEngine.
- **No regression** (flag ON, throwaway :8791 engine, live Neo4j): `context_eval` **8/8**
  (also 8/8 flag OFF), `proactive_eval` 12/15 (in the 11–14 model-noisy band), suite fail-set
  unchanged. The live Neo4j is DETACH-DELETE cleaned after every run.

## Still open (future phases, per cozy-chasing-comet.md)
- **Style learning** — nothing yet learns *how you write* (needs real sent-message history).
- **ANN** — cosine retrieval is still O(n); an approximate-NN index is the remaining scale item.
