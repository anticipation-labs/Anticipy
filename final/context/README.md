# final/context — the ONE final context / memory system  [STATUS: PARTIAL]

The "context engineering / vector" layer. What lets the brain **retrieve the right facts** when you
say "the usual Friday update" or "email Sam," and **learn you** over time so it never re-asks.

## What works today
- Stores facts in typed drawers (people, preferences, open loops), per-user isolated.
- Retrieves them into the brain's context on each turn.

## What's NOT done (the real gap)
1. **Learns your style** — nothing yet learns *how you write*, so drafts aren't in your voice.
2. **Never re-asks** — no ledger that guarantees a known fact is never asked twice.
3. **Resolves references** — "the boss", "the usual place" → the actual thing, ask-once-on-miss.
4. **Semantic retrieval** — retrieval is by drawer/keyword, not meaning; a vector index is the upgrade.

## Done when
`final/tests/context_eval.py` (many-case, to be written) shows: it drafts in your voice, resolves
"the usual" correctly, and **never re-asks a fact it already knows** — across varied cases.

## Where the real code assembles
`live_memory/` (the drawers + retrieval) + ported `resolve_reference` + a new `style_profile`.
