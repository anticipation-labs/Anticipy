# Room 4 — Real Channels + the Ask Round-Trip

## Recipe (from current practice, last-12-mo sources)
- Durable human-in-the-loop = **pause → persist state → resume on a signal/reply** (Temporal
  Signals; LangGraph interrupt()+checkpointer). The paused work is durably recorded as waiting
  for a condition; the user's reply is the signal that resumes it. SMS (Twilio) is the notify
  channel; the reply flows back to the waiting work.
- **Idempotent resume**: anything before the interrupt that charges money / writes data must be
  idempotent. So: do NOT execute the detrimental action at ask-time; only on approval.

## Design
- **The ask round-trip (the core deliverable):**
  - Detrimental verdict (Room 2) → engine creates `Goal(state=waiting)`, PERSISTS it (the
    orchestrator's GoalStore — same store that already resumes waiting goals), and does NOT run
    it. Registers a pending ask {ask_id → goal_id, action, channel}. Sends the ask over a
    channel. Hard gate: the goal is WAITING (no step executed) until approved — no silent harm.
  - `resolve_ask(ask_id, approved)`:
    - YES → `orchestrator.start_goal(goal)` → runs the EXACT paused goal to done (the resume).
    - NO  → goal → failed/dropped; write the decline to memory (`write_memory` via the bus) so
      Room 5 can suppress that action-type next time.
- **Real channels (replaces the channel stub + the wall-handler stub):**
  - `channels/text.py::TextChannel` — REAL Twilio SMS when `ANTICIPY_CHANNELS_MODE=live` and
    creds present (TWILIO_ACCOUNT_SID / AUTH_TOKEN / FROM); otherwise MOCK (records the message,
    returns sent=mock). CI uses mock → free + deterministic.
  - `channels/app.py::AppChannel` — in-app ask queue the SwiftUI app surfaces (Room 6).
  - Money/irreversible sends stay MOCKED except ONE controlled real proof to a test target —
    that proof needs the user's Twilio creds + a test number (a one-time human action, like the
    Gmail OAuth / extension-load proofs). Every real send is logged.

## Test (written before the impl)
`engine/scripts/test_ask_roundtrip.py` — a detrimental event → engine PAUSES (waiting goal, NOT
executed) + a message goes out on a MOCK channel → `resolve_ask(yes)` → the waiting goal RESUMES
and reaches done (assert the resume + the goal state, not just the send). A second event →
`resolve_ask(no)` → goal dropped + the decline written to memory. Deterministic; zero real sends.

## Sources
- Temporal — Durable Human-in-the-Loop (Signals): https://learn.temporal.io/tutorials/ai/building-durable-ai-applications/human-in-the-loop/
- LangChain/LangGraph — Durable execution (interrupt + checkpoint, idempotency): https://docs.langchain.com/oss/python/langgraph/durable-execution
- Twilio — long-running async operations: https://www.twilio.com/en-us/blog/handle-long-running-asynchronous-operations-studio
