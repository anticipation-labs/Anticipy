# Room 1 — Triage Gate (the bouncer; cheap, first, the cost spine)

## Recipe (from current practice, last-12-mo sources)
- **Cascade / tiered triage.** Cheap deterministic pre-filter runs FIRST and drops the bulk
  of ambient noise; the expensive stage (smart model / harm-line) only sees survivors. This
  is the standard shape for high-noise streams — SOC alert triage runs at ~99% false-positive
  and uses exactly this divide-and-conquer (cheap filter → reasoning agent).
- **Tune the cheap tier for HIGH RECALL, not precision.** A dropped real event is
  unrecoverable; a passed junk event is killed cheaply at the next stage. So when unsure,
  PASS. The hard bar for the cheap tier is recall≈1.0 on real/actionable; precision can be
  imperfect (the harm-line is the precision backstop).
- **Deterministic default, cheap-model tiebreak behind the flag.** The first tier is pure
  rules (zero model calls, CI-safe + free). A cheap-model branch handles genuinely ambiguous
  events ONLY under live mode — never in stub/CI. This is the cost spine: the gate kills the
  ~99% before any smart call, so runtime cost stays under the ~$0.82/user/day ceiling.
- **General signals only** (no site/test-specific branches): actionable VERBS (send, book,
  email, call, pay…), commitment/request/imperative patterns ("I'll", "remind me", "need to",
  "can you", deadlines), and negative signals (fillers, greetings, bare observations).

## Design
`proactive/triage.py::Triage.actionable(text) -> bool`
- positive: any action verb (word-boundary) OR any intent/commitment regex (I'll / remind me /
  need to / can you / let's / by <day> …)
- negative: empty / sub-2-token / pure filler ("um", "ok thanks", "hey") → drop
- ambiguous (no positive, not filler) → drop in stub; in LIVE a cheap-model tiebreak MAY
  rescue it (behind the flag; never in CI). Bias of the tiebreak: pass when in doubt.
- ProactiveEngine calls Triage first; dropped events never reach the gate (zero smart calls).

## Test (written before the impl)
`engine/scripts/test_triage.py` — a replayed labeled stream (~75% noise, ~25% real, incl.
tricky cases). Assert BOTH directions: recall on real == 1.0 (nothing real dropped, the hard
bar) AND noise-drop rate high; and ZERO smart-model calls during triage (the cost spine).
Report the realized counts straight.

## Sources
- IBM — Alert Fatigue Reduction with AI Agents: https://www.ibm.com/think/insights/alert-fatigue-reduction-with-ai-agents
- CORTEX: Collaborative LLM Agents for High-Stakes Alert Triage (2025): https://arxiv.org/pdf/2510.00311
- thunlp/ProactiveAgent (ICLR 2025): https://github.com/thunlp/ProactiveAgent
- ProActLLM workshop (proactive conversational AI): https://proactllm.github.io/
