# Memory consolidation + the profile layer (roadmap §1)

Written 2026-08-04, brief 05. Code: `brain/memory.py` (the layer),
`brain/worker.py` (the nightly hook), `tests/test_memory_consolidation.py` +
`tests/test_worker_consolidation.py` (the proof).

## The problem

The graph memory keeps every mumble raw forever, and weighs a grocery
mumble the same as "my mom is in hospital". Nothing accumulates ABOUT the
owner — recall is term-hits over episodes, so being known never happens.

## What was built

A **profile layer** on top of the raw graph. Raw episodes are untouched and
never deleted — they are the audit trail. The profile is a lens over them.

### The schema (additive — an existing memory file opens unchanged)

Two tables, both `CREATE TABLE IF NOT EXISTS`, in the same SQLite file:

```
profile_facts
    fact           the distilled note ("partner is Sarah")
    importance     1-5, model-judged at distillation (5 = family, health,
                   hard boundaries; 3 = solid preference or ongoing project;
                   1 = mildly useful color)
    confidence     starts 0.6 (consolidation) / 0.9 (interview seed),
                   +0.15 per re-observation, capped 0.99
    source         consolidation | interview | import
    provenance     JSON list of the episode ids the fact came from
    first_seen_ts / last_seen_ts

consolidation_state
    key/value: last_episode_id (the cursor), last_run_ts
```

### The pass — `Memory.consolidate()`

Nightly (and callable on demand). One pass:

1. Read episodes with `id > last_episode_id`, up to a batch (200).
2. Ask the model (CONSOLIDATE_SYSTEM) to distill STABLE facts — things true
   for weeks, worth knowing him by — each with importance and the episode
   ids it came from. One-off logistics and small talk are explicitly not
   facts.
3. A fact whose episode ids don't check out against the batch is dropped:
   nothing unevidenced gets written, same doctrine as commitments.
4. Each candidate is checked against the existing profile (dedup, below):
   merge or insert.
5. Advance the cursor and stamp the run — **in the same transaction as the
   writes**. A crash mid-pass commits nothing; the same episodes are simply
   read again next time. Idempotent, incremental, nothing lost.

With `llm=None` the pass returns `ran=False` and touches nothing — the
profile stays empty, nothing crashes, hearing is never affected.

### Dedup — restatements merge, they don't multiply

`_find_same_fact()`: identical-after-normalization (possessives folded)
merges with no model; word-overlap 0.8+ merges as near-identical; overlap
0.4–0.8 is put to the model as a same-fact judgment (SAME_FACT_SYSTEM).
A merge keeps the original wording, takes the higher importance, bumps
confidence, extends provenance, and refreshes `last_seen_ts`. The same
plan restated five ways is one row with five pieces of evidence.

### Salience-aware recall

`recall()` now consults the profile FIRST, ranked
**importance × recency × relevance** (recency is a 30-day half-life on
`last_seen_ts`, relevance is query-term hits), then lets the raw
graph/episode search fill the rest of the window. So "mom is in hospital"
outranks thirty grocery mumbles that match more words. Profile entries come
back as `known: <fact>` with `src_type="profile"`, which means triage
context (`anticipy_core._decide` reads `recall()`) prefers profile facts
with no change of its own. `briefing_facts()` leads with the profile too;
`heard` and `open_loops` keep their exact old shape.

### The seed API — `remember_fact(text, importance, source="interview")`

Day zero (§8) writes the interview answers straight into the profile here:
validated, importance clamped 1–5, deduped through the same merge path, so
re-posting an answer can never dupe. Works with no LLM.

### The nightly hook — `worker.run_nightly_consolidation()`

Guardrails outside the model, like the clock's: only in the clock's quiet
hours (22:00–08:00, owner asleep), at most once per ~20h, at most 10
batches a night. Cursor and stamp live in the memory DB itself, so a
redeploy resumes instead of repeating. A Memory with no live LLM is skipped
outright, and any failure is printed and swallowed — consolidation must
never take hearing down with it. Because only success stamps the run and
the hook fires on every poll tick, a failed attempt also arms a 30-minute
retry gap — a flaky night retries gently instead of calling the model
every two seconds until dawn.

## What deliberately did NOT change

- Raw episodes: kept forever, never rewritten. The FTS index, the graph,
  open loops, close-from-speech — all untouched.
- No new env vars, no new files on disk, no network beyond the existing
  LLM client.
- Recall with an empty profile is byte-for-byte the old behavior.
