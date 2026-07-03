# MEMORY — WAKE-UP REPORT (built overnight 2026-07-02 → 07-03)

## The headline
**The memory scoreboard went 3/8 → 8/8. All 8 cases pass.** Verified twice on the committed code
(HEAD `55d4f7e`), on a throwaway engine with a fresh data dir — **your real memory on :8790 was
never touched.** No regression: suite stayed 113/9 (byte-identical fail-set), every change committed
and reversible.

## Run it yourself (30 seconds)
```
cd ~/Anticipy-devin
TMP=$(mktemp -d); ANTICIPY_CHANNELS_MODE=mock ANTICIPY_HANDS_MODE=mock ANTICIPY_DATA_DIR="$TMP" \
  PYTHONPATH=engine engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8791 &
ANTICIPY_ENGINE_URL=http://127.0.0.1:8791 engine/.venv/bin/python final/tests/context_eval.py
```

## What now works (the 8 cases)
1. Never re-asks the dentist (uses what you told it) · 2. Resolves "my usual" → the stored order ·
3. Disambiguates two Sams (picks the right one or asks) · 4. Drops a fact that went stale
(bi-temporal) · 5. Surfaces a relevant known fact (allergy) when it matters · 6. Handles a retraction
("never mind" cancels it) · 7. Applies a standing preference ("never before 9am") · 8. Never re-asks
your address.

## What got built (all committed, in `final/context/`)
- **Phase 2** — memory into the deciding brain (it no longer decides blind).
- **Phase 3** — the learns-you engine: resolve "the usual", person dossiers, retraction handling,
  never-re-ask ledger, + deterministic fact-capture (the pipeline used to drop pure facts).
- **Phase 5** — the browser now writes back what it learns instead of throwing it away.
- **Phase 6** — idle self-consolidation (dedupe, decay, generalize).
- **Case 7 fix** — standing preferences now persist as durable preferences and get applied at
  scheduling.

## Honest notes (so nothing surprises you)
- **This is the no-keys ceiling — genuinely final without the cloud stack.** The two cases we
  thought needed keys (semantic allergy, two-Sams) already pass on-device.
- **What your cloud keys still DEEPEN** (they add robustness, not eval points): Voyage/Gemini +
  Turbopuffer = real embeddings so semantic recall survives paraphrase at scale (today it's an
  on-device hashed+keyword store); Neo4j/Graphiti = a real temporal graph for true multi-hop person
  disambiguation; a reranker tightens precision. That's Phases 1 & 4 — a flip away once keys land.
- **The GEMINI_API_KEY in this environment is invalid**, so the "smart decider" path from Phase 2
  runs on a fallback; the 8/8 is earned by the deterministic learns-you engine + grafts (which is a
  good thing — it means memory works even with no model key).
- **Heads-up on proactive:** re-running `proactive_eval.py` shows an 11–14/15 band (live-model
  noise on multi-task splitting) — pre-existing, NOT caused by the memory work. Worth a look when we
  return to the brain.

## What's left overall (not memory)
Browser agent (the real screenshot-first + voting plan), the proactive multi-task-splitting noise,
and leg 5 — a real person carried through a real day. Memory itself is done to its no-keys ceiling.
