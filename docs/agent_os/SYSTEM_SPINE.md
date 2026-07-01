# SYSTEM SPINE — how Anticipy flows together (one system, not separate plumbing)

> Standing doc. Every agent reads this before touching any single component. A piece is only
> "done" when it works **inside this spine on a real day**, never in isolation.

## The one loop (this is the product)

```
  EAR              MEMORY              DECIDER            HANDS               VOICE/TEXT
  ───              ──────              ───────            ─────               ──────────
  hear a  ─►  capture + infer   ─►  triage → decider  ─►  do it for real  ─►  close the loop
  messy       (episodic log,        → harm-line        (browser in your     ("event made;
  day         derived facts,        (act / ask /        own Chrome, or       I'll call at 2:45")
              routines)             silent; money       API connectors)
                     ▲              is the only         │                          │
                     │              hard stop)          │                          │
                     └──────────── verify + write back ─┴──────────────────────────┘
                                   (read-back is the only proof of done)
```

One Event enters; it is remembered, decided on, executed, verified, and the loop is closed
back to the person. Memory is read BEFORE the decision and written AFTER the action — that is
what makes the components one system instead of four pipes bolted together.

## Where each piece lives (grounded in the code)

| Stage | Module | Role |
|-------|--------|------|
| Ear / intake | `capture/`, `channels/` (text, call, inbound, relay) | turn a day into Events |
| Memory | `live_memory/` (`brain.py` = capture·inject·infer·maintain·selfcheck), `memory/store.py` | hot write, hot read (inject context), cold infer routines, retrieval audit |
| Decider (proactive) | `core/proactive.py` + `proactive/` (triage · decider · harm · budget · digest) | drop the 99% noise, decide ACT/ASK/SILENT, money = hard stop |
| Orchestrator | `core/orchestrator.py`, `core/control_core.py`, `core/worker.py`, `core/bus.py` | turn a decision into a Goal, route it to a hand, run it |
| Hands | `hands/api_hand.py` (Arcade: Calendar/Gmail), `hands/browser_hand.py` + `agent/webvoyager.py` + the MV3 extension | do it for real |
| Voice/text | `core/voice.py`, `channels/text.py`, `channels/call.py` | close the loop back to the person |
| Glass box | `core/glassbox.py`, `core/scorecard.py` | every decision + result recorded, inspectable |

## Status of the two components in question

- **Proactive engine (the decider): built and wired.** `core/proactive.py` runs the real
  triage → decider → harm-line path; money is the only hard stop; every decision is recorded to
  the glass box + scorecard. Proven via the persona/real-day eval harness, NOT in isolation.
- **Browser agent (the hands): built and wired, product-done.** MV3 extension (trusted CDP input
  in the user's own logged-in Chrome) + engine loop (`agent/webvoyager.py`): vision-first
  Set-of-Marks grounding, cheap→frontier routing, recipe replay (~$0 on repeats), money hard-stop.
  Measured on the public WebVoyager sample: **43% cold, ~$0.19/task** (below Browser-Use's ~50%).
  → **Done as a product component. NOT the "#1 in the world on the public benchmark" title** —
    that is a separate, still-open checkbox and must never be conflated with product-done.

## The rule that keeps it one system (not separate plumbing)

Before a component is called done, it must be exercised **through the spine end to end**:
a real Event goes in one side and the loop closes on the other, with memory read before and
written after. The factory's real-day / persona eval is exactly this whole-loop test — that is
why "a single piece is never done in isolation" is a law, not a preference.

## What comes next on the spine: MEMORY + CONTEXT ENGINEERING

Memory is the weakest link that makes the *other* pieces smart. It is next because the decider
and the hands are only as good as the context injected into them. Concretely:

1. **Retrieval quality (inject).** The decider and hands must get the *right, complete* memory
   for this Event — not everything, not stale facts. Measure with `live_memory/selfcheck.py`
   (relevant + complete recall); grind precision/recall on real days.
2. **Inference depth (infer).** Derive routines / recurring people / standing preferences as
   DERIVED facts (never auto-promoted past confidence 1.0). This is what lets the agent
   *anticipate* instead of react.
3. **Context assembly (the prompt the model actually sees).** One disciplined context builder
   that assembles profile + relevant episodic + derived + current Event into the decider's and
   the hands' prompts — so memory, decision, and action share ONE context, not three.
4. **Write-back after action.** Every executed Goal writes its outcome back to memory so the
   next decision is better. This closes the flywheel (and feeds recipe replay on the hands).
5. **Proof.** Real-day eval where a fact learned on day 1 changes an action on day 3, verified
   by the judge — the whole-loop test, not a unit test.

Done-gate for this phase: recall metrics up on real days AND a learned fact demonstrably changes
a later action, judge-verified — never "the retrieval unit test passes."
