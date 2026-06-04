# Room 3 — The Trigger Model (the alarm clock; what makes it anticipatory)

## Recipe (from current practice, last-12-mo sources)
- Proactive agents WATCH for conditions and act when met — a shift from reactive Q&A.
  Formalized as **Intent-Conditioned Monitoring** (formulate trigger conditions from what the
  user said) + **Event-Triggered Follow-up** (engage the user when a condition fires).
- **Time/scheduled triggers** run on a clock (timer/cron): a tick re-evaluates conditions.
- **Fire-once / idempotency**: a fired condition must not re-fire on the next tick (no storms).
  Standard approach = a dedup key per fired condition.

## Design
- The ledger is the condition source: the open_loops drawer (the user's commitments).
- `MemoryWorker` gains a READ intent `list_open_loops` (additive) → structured loops
  {id, task, due, due_ts, created_ts, status}. The engine still consumes memory via the bus;
  it never reaches into the stores directly.
- `proactive/trigger.py::TriggerWatcher.tick(loops, now)` → the loops whose condition is met:
    - TIME: `due_ts` present and `<= now`  ("you said you'd email Sarah Friday; it's Friday")
    - ELAPSED: no due_ts and open for `>= stale_after`  (a commitment going stale → nudge)
  Fires each EXACTLY once via an in-memory fired-id set (session-scoped; persisting the mark
  across restart is a noted refinement — and due-TIME extraction from "Friday"→due_ts is a
  capture enhancement; the watcher mechanism is what Room 3 delivers).
- `ProactiveEngine.trigger_tick(now)`: list_open_loops → watcher.tick → for each fired loop,
  synthesize a `system` Event ("Follow up on your commitment: <task>") and run it through the
  SAME on_event path (triage → harm-line → act/ask). So a due send-commitment still ASKS; a
  due research-commitment ACTS. Logs `trigger_fired` to the glass-box.

## Test (written before the impl)
`engine/scripts/test_trigger.py` — plant open_loops with controlled due_ts/created_ts. Assert:
a DUE loop and an ELAPSED loop each fire a proactive goal/ask with NO new input event; a
not-due / fresh loop does NOT fire; a second tick at the same clock fires NOTHING (fire-once);
a fired safe commitment → ACT (goal), a fired send commitment → ASK. Deterministic.

## Sources
- MindStudio — The Post-Prompting Era (reactive→proactive): https://www.mindstudio.ai/blog/post-prompting-era-proactive-ai-agents
- Microsoft Agent Academy — Add Event Triggers to act autonomously: https://microsoft.github.io/agent-academy/operative/04-automate-triggers/
- Long-term Task-oriented Agent (Intent-Conditioned Monitoring, Event-Triggered Follow-up): https://arxiv.org/pdf/2601.09382
- ProActor — Timing-Aware proactive task scheduling (ACL 2026): https://arxiv.org/html/2605.24900v1
