# Brief 07 — Segment-fed triage context (roadmap §2)

## Mission
A 70-second pause mid-plan makes her treat the resumption as a new subject.
The smart conversation-boundary engine already exists (`brain/segmenter.py`:
45s free continuation, topic-overlap/anaphora up to 20 min, hard cut after,
capture-time keyed) — but the live hearing path only carries the previous
single line if < 120s old. Wire the segmenter INTO triage: the triage
context becomes the current segment's lines, not "last line if < 120s".

## Context you must read first
- `brain/segmenter.py` — whole file, especially how segments accrete and close.
- `brain/anticipy_core.py` — hear(), `_prev`, `_decide` (prev_line, convo,
  prev_addressee plumbing), and the addressee stickiness (120s window).
- `brain/worker.py` — where transcript events flow into hear(), and whether
  the segmenter is instantiated there today.
- `proof/test_segmenter.py` — the existing behavioral contract.

## Design constraints (non-negotiable)
- The segmenter's decisions are the ONE source of continuity: `_prev`'s
  120s rule and the addressee 120s window both defer to segment membership
  (same segment = carried context + sticky addressee; new segment = fresh).
- Cap what rides into the prompt (last ~6 lines of the segment) — token
  discipline; do not paste whole segments.
- Lines already acted on must not re-enter context as fresh material
  (the existing duplicate-job guard must keep holding).
- Late/backlogged data (capture-time old) is remembered but never acted on —
  preserve the segmenter's LATE_MAX_S contract.
- Zero changes to segmenter thresholds; this is wiring, not retuning.

## Definition of done
- Offline tests: a 70s pause same-topic keeps context (the roadmap's exact
  complaint); a 25-min gap or topic change drops it; acted lines don't
  re-trigger; late backlog stays ambient. Existing segmenter + core suites
  all still green.
- All existing suites green (PYTHONPATH=. python3 proof/test_*.py; pytest tests).

## Rules
Work only in this repo copy. Do NOT touch production, do NOT push, do NOT
edit files outside brain/ + tests/ + proof/. Commit scoped work, print
DONE + summary.
