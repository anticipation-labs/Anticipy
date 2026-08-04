# Brief 04 — Three-lane delivery (roadmap §3)

## Mission
She has only two volumes today: silent, or a text. Build the middle lane.
Work ALWAYS happens; delivery is what changes:
1. **ambient** — remembered, visible in the app feed if he looks. No push, no SMS.
2. **desk** — work she did on her own (research results, options, drafts)
   lands as a feed entry (`anticipy_says` event). Never SMS.
3. **shoulder tap (SMS)** — ONLY when (a) she is blocked on his confirmation,
   (b) he asked over SMS (reply in-thread), or (c) a genuinely time-critical
   deadline (< 3 h) would otherwise be missed.

## Context you must read first
- `brain/worker.py` — report_finished_jobs, report_stuck_jobs, report_stalled_work,
  the clock, `ambient_job`, the research-lane desk delivery (already partial lane logic).
- `brain/anticipy_core.py` — hear(), `_queue_job` (lane + channel params),
  the ambient addressee path.
- `brain/conversation.py` — the SMS thread and `_think`.
- `design/PRODUCTION-ROADMAP.md` §3.

## Design constraints (non-negotiable)
- The lane decision is DETERMINISTIC, outside the model: a single function
  `delivery_lane(job|event) -> "ambient"|"desk"|"sms"` with the three rules
  above, unit-testable. The model may propose; the rule decides.
- Existing behaviors that must NOT change: confirmation questions for held
  jobs still go out (they are "blocked on him" = SMS lane); direct SMS asks
  still answered over SMS; quiet hours + 4h clock gap + may_say dedup all
  still hold for anything SMS-bound.
- Ambient/desk deliveries never call SMS send paths, ever.
- Unify the two partial lane mechanisms that already exist
  (`params.lane == "ambient"` from addressee work, `job.lane == "research"`
  from the research arm) under the one delivery_lane rule — do not add a third.
- No schema changes unless truly needed; prefer params/existing fields.

## Definition of done
- Offline tests: each lane's rules, incl. the deadline rule and the
  blocked-on-confirmation rule; regression tests proving confirmations and
  SMS-asked answers still text.
- All existing suites still green (PYTHONPATH=. python3 proof/test_*.py, and
  python3 -m pytest tests).
- A short manager-runnable proof plan (markdown) describing how to verify
  live: a research job queued from the app lands on the desk with no SMS;
  an SMS-asked job replies in-thread; a held job still asks.

## Rules
Work only in this repo copy. Do NOT touch production, do NOT push, do NOT
edit files outside brain/ + tests/ + proof/ + design/. Commit scoped work
with a clear message, print DONE + summary.
