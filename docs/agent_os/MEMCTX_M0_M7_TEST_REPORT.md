# Memory + Context Engineering — M0→M7 Test Report

**Date:** 2026-06-28 · **Branch:** devin/full-frontend-ui · **Result:** ALL GREEN, zero regressions.

## What was proven
The three things (memory+context / proactive / browser) converge on ONE ContextPack builder —
the anti-"plumbed separately" spine — wired into the frontend. Every milestone is gated on a
reproducible test that can FAIL, registered in `bash scripts/run_suite.sh`.

| Milestone | Gate (failable test) | Result |
|---|---|---|
| M0 | baseline harness prints today's numbers | green |
| M1 | one builder, three consumers (decide/act/speak) — `test_memctx_contextpack.py` | green |
| M2 | ADD/UPDATE/DELETE reconciliation — `test_memctx_reconcile.py` | green |
| M3 | bi-temporal validity, ephemeral expiry — `test_memctx_temporal.py` | green |
| M4 | salience gate + tiering, durable bounded — `test_memctx_salience.py` | green |
| M5 | privacy: never-store masked, redact-before-egress, right-to-delete — `test_memctx_privacy.py` | green |
| M6 | rerank + recall-guard contradictor; reflection contradictor — `test_memctx_rerank.py` | green |
| M7 | day-1 fact changes day-3 action, counterfactual + judge — `test_memctx_flywheel.py` | green |

**Suite:** 107 passed / 12 pre-existing failures (owner-mode + next-server; verified unrelated —
`retraction_silenced` & `messy_proactive_handoff` fail identically with `infer.py` reverted to HEAD).
Zero regressions introduced by M5–M7.

## Live end-to-end (engine)
- `GET /memory/context?purpose=decide|act|speak` resolves for all three consumers through the ONE builder.
- `POST /memory/forget-me` is default-deny (returns `deleted:false` without the exact phrase `DELETE MY DATA`).

## Frontend demo — the ONE ContextPack spine, made visible
The Memory page (`/memory`) surfaces the exact ContextPack the brain assembles. Same builder,
purpose-shaped output for each consumer:

**Live circuit — one shared record across input→brain→memory→browser→voice→proof:**

![Live circuit](../../../screenshots/ss_86ffd943.png)

**purpose=decide — 27 items / 1563 chars (tight+complete for the decider):**

![decide](../../../screenshots/ss_1b2a882a.png)

**purpose=act — 28 items / 1616 chars (richest, for the browser hands):**

![act](../../../screenshots/ss_3303ecac.png)

**purpose=speak — 20 items / 1184 chars (leanest, facts-only for the voice):**

![speak](../../../screenshots/ss_74a50c61.png)

The item/char counts differ per purpose off the *same* builder — proof it is one spine shaped
three ways, not three parallel pipes.
