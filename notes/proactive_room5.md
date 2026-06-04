# Room 5 — The Annoyance Budget (wearable 365 days)

## Recipe (from current practice, last-12-mo sources)
- An interruption is a **withdrawal from a finite daily account**, not a deposit. Proactive
  agents hit a **hard ceiling of ~3–5 notifications/day** before users disable them (and ~52%
  of users who disable push churn). So cap proactive interruptions hard.
- **Learn from dismissals, per-category.** A user who dismissed the last few of a kind has
  implicitly raised their threshold for it — stop proposing that type.
- Users **prefer SUPPRESSING over deferring** undesired interruptions.

## Design — `proactive/budget.py::AnnoyanceBudget`
- Counts only **PROACTIVE interruptions** (asks the ENGINE initiates, i.e. `source=system`
  trigger-fired asks). USER-initiated asks are never suppressed — the user is present and asked.
- A proactive ask is **suppressed** when: its action-type was DECLINED before (the Room 4
  decline signal — same signal, per Deferred-1), OR the daily interruption count is at the cap.
- Action-type signature = harm category + the salient content tokens (len≥4, non-stopword), so
  "email the investor about the deck" suppresses the same type but not "research flights".
- A SAFE proactive action does NOT interrupt (act-first acts silently) → it never spends budget;
  only ASKS count. A suppressed detrimental action is NOT executed and NOT asked — it's dropped
  (no silent harm, no annoyance), the safe outcome research prefers.
- **DECISIONS-ONLY-OMAR:** the cap NUMBER is a taste call. Built configurable
  (`max_per_day`), defaulted to **5** (top of the research 3–5 ceiling); the exact value is
  Omar's — logged, not auto-decided. (Timing-of-day sense beyond the daily cap is a noted refinement.)

## Test (written before the impl)
`engine/scripts/test_annoyance.py` — replay a day of PROACTIVE detrimental asks: interruptions
sent stay ≤ the configured cap (the rest suppressed as over-budget); separately, after the user
DECLINES an action-type, the SAME proactive action-type is suppressed on its next occurrence
while a different type still goes through. Deterministic; controlled clock.

## Sources
- TianPan — Background Agents and the Notification Budget (3–5/day ceiling): https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy
- ProMemAssist — timely proactive assistance on wearables (working-memory timing): https://arxiv.org/html/2507.21378v1
- Courier — Reduce Notification Fatigue (7 strategies): https://www.courier.com/blog/how-to-reduce-notification-fatigue-7-proven-product-strategies-for-saas
- A Snooze-less User-Aware Notification System for Proactive Conversational Agents: https://arxiv.org/pdf/2003.02097
