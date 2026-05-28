# V7 Persistence Simulation Summary

Generated: 2026-05-28T04:09:41.282821Z

## Bottom line

- Part A (cross-session continuity): PASS
- Part B (7-day stress): PASS

## Part A: cross-session continuity

- Account: `persistence_sim_2026_05_28_a`
- Dossier: `/Users/omarebrahim/.anticipy/v7/dossiers/persistence_sim_2026_05_28_a/dossier.json`
- People persisted: 5/5 (100.0%)
- Topics persisted: 5/5 (100.0%)
- Cross-reference: "my dentist" -> Marisol: RESOLVED (intent type=remind, refs=['Marisol'])

## Part B: 7-day stress

- Account: `persistence_sim_2026_05_28_b`
- Dossier: `/Users/omarebrahim/.anticipy/v7/dossiers/persistence_sim_2026_05_28_b/dossier.json`
- Days completed: 7 / 7
- Total transcripts: 35
- Reference attempts: 19
- References resolved: 19 (100.0%)
- Dossier monotonic growth: True

### Per-day breakdown

| Day | People after | New | Refs attempted | Refs resolved | % |
|---|---|---|---|---|---|
| 1 | 4 | 4 | 0 | 0 | None |
| 2 | 6 | 2 | 3 | 3 | 100.0 |
| 3 | 8 | 2 | 3 | 3 | 100.0 |
| 4 | 10 | 2 | 3 | 3 | 100.0 |
| 5 | 12 | 2 | 3 | 3 | 100.0 |
| 6 | 14 | 2 | 3 | 3 | 100.0 |
| 7 | 15 | 1 | 4 | 4 | 100.0 |

## Artifacts

- Part A result: `state/v7/persistence_cross_session/20260528T035757Z/result.json`
- Part B result: `state/v7/persistence_7day/20260528T035931Z/result.json`

## What this proves

1. The per-account dossier file at `~/.anticipy/v7/dossiers/<account_id>/dossier.json` survives a close-and-reopen cycle (the cross-session boundary the engine's dossier_active_loader uses on every restart).
2. The LLM-backed intent extractor (`/api/intent/extract`) resolves vague references like "my dentist" or "Solange" to the right person when the dossier is supplied via `memory_context`.
3. Across 7 simulated days, the dossier accumulates monotonically and day-N transcripts that reference day-N-1 entities can be resolved at the rate reported above.
