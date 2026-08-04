# Brief 05 — Memory consolidation + profile layer (roadmap §1)

## Mission
The graph memory (episodes/nodes/edges) keeps every mumble raw forever and
weighs a grocery mumble the same as "my mom is in hospital". Build the
layer that makes memory feel like being KNOWN:
- **profile facts**: a nightly (and on-demand) consolidation pass reads
  recent episodes and distills stable facts ("partner is X", "prefers 7pm
  dinners", "works on Anticipy") with importance (1–5), confidence,
  provenance (episode ids), first/last seen.
- **dedup**: near-identical facts merge (LLM-judged same-fact), updating
  last_seen + confidence instead of duplicating.
- **salience-aware recall**: recall ranks by importance × recency ×
  relevance; profile facts are consulted FIRST, raw episode search second.
- Raw episodes stay forever (audit); nothing is deleted.

## Context you must read first
- `brain/memory.py` — whole file: SCHEMA, ingest, recall, open_loops,
  briefing_facts.
- `brain/worker.py` — where a nightly pass would hook (the clock), and how
  memory persists (`ANTICIPY_MEM` path / /data volume).
- `brain/llm.py` — the LLM interface; consolidation must degrade gracefully
  with llm=None (skip pass, never crash).
- `design/PRODUCTION-ROADMAP.md` §1 and §8.

## Design constraints (non-negotiable)
- SQLite only, same DB file, additive migrations in-code (CREATE TABLE IF
  NOT EXISTS) — existing memory files must open unchanged.
- Consolidation is idempotent and incremental (tracks last consolidated
  episode id); a crash mid-pass loses nothing.
- briefing_facts() and triage context prefer profile facts over raw lines.
- A seed API: `remember_fact(text, importance, source="interview")` — the
  hook §8's day-zero interview will write into.
- No new required env vars; no network beyond the existing LLM client.

## Definition of done
- Offline tests with a mocked LLM: extraction -> profile rows with
  provenance; dedup merges restatements; salience ranking beats raw
  term-hits; llm=None path is a no-op; existing Memory tests still green.
- All existing suites still green.
- A markdown note (design/memory-consolidation.md) documenting the schema
  and the pass, in the codebase's plain-spoken style.

## Rules
Work only in this repo copy. Do NOT touch production, do NOT push, do NOT
edit files outside brain/ + tests/ + proof/ + design/. Commit scoped work,
print DONE + summary.
