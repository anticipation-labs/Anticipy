"""Room 1 test — the triage gate (the bouncer).

Replays a labeled stream (mostly noise + clearly-actionable real events, incl. tricky
word-boundary and intent-only cases) through the REAL Triage, against the STUB gateway.
Asserts BOTH directions and the cost spine:
  - recall on REAL == 1.0  (nothing actionable dropped — the hard bar)
  - noise-drop rate high    (the bouncer earns its keep)
  - ZERO smart-model calls during triage (the ~99%-killed-before-the-smart-model spine)
Reports the realized counts straight. Zero model calls; deterministic; CI-safe.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_triage.py
"""
import sys

from anticipy_engine.core.gateway import ModelGateway
from anticipy_engine.proactive.triage import Triage

# (text, is_actionable) — labels NEVER enter triage.actionable(); used only to score.
STREAM = [
    # --- clearly actionable (MUST survive: verb / commitment / request / deadline) ---
    ("I'll send Sarah the Q3 deck on Friday.", True),
    ("Remind me to call the dentist tomorrow.", True),
    ("Wire money to the contractor.", True),
    ("I need to email the accountant by Thursday.", True),
    ("Can you book a table for two tonight?", True),
    ("Let's reschedule the standup to 3pm.", True),
    ("Don't forget to renew the car insurance.", True),
    ("I should follow up with Dana about the contract.", True),
    ("Buy more coffee filters.", True),
    ("Set up a meeting with the design team.", True),
    ("I have to cancel my gym membership.", True),
    ("Please forward the invoice to finance.", True),
    ("I should really get back to Mom this week.", True),   # intent-only, no listed verb
    ("The rent is due by the first.", True),                # deadline-only -> a task
    ("We need to confirm the venue.", True),                # commitment
    ("Order a new charger.", True),                         # bare imperative verb
    ("Eventually we need to confirm the venue by Friday.", True),  # hedge CANCELLED by a time anchor
    # --- ambient noise (SHOULD drop: filler / greeting / bare observation) ---
    ("um", False), ("ok thanks", False), ("hey", False), ("yeah", False), ("hmm", False),
    ("Cool, sounds good.", False),
    ("The weather is nice today.", False),
    ("I'm so tired this morning.", False),
    ("That movie was great.", False),
    ("Traffic was bad on the way in.", False),
    ("My coffee is cold.", False),
    ("The sunset looked amazing.", False),
    ("I had eggs for breakfast.", False),
    ("It's pretty cold outside.", False),
    ("The game went late last night.", False),
    ("She seems nice.", False),
    ("My back hurts.", False),
    ("Just relaxing today.", False),
    ("lol that's funny", False),
    # --- tricky noise: contains an action SUBSTRING but isn't a task (word-boundary must reject) ---
    ("I love sending postcards.", False),     # "sending" != \bsend\b
    ("The meeting was productive.", False),   # "meeting" != \bmeet\b
    ("I already sent it earlier.", False),    # past-tense, done; "sent" != \bsend\b
    ("The buyer seemed happy.", False),       # "buyer" != \bbuy\b
    # --- vents: hedge-NONSPECIFIC commitments (positive cues present, no time anchor) must drop.
    #     Asking on these is the gate-S3 failure; acting on them is the cardinal sin. ---
    ("Ugh, I should really call the plumber someday.", False),
    ("I'll deal with the gutters eventually.", False),
    ("Should probably get that espresso machine at some point.", False),
    ("I need to sort out my closet one of these days.", False),
    ("I'll renew my passport when I get a chance.", False),
]


def main():
    gw = ModelGateway()  # stub; triage must never touch it
    tri = Triage(gateway=gw)

    real = [s for s in STREAM if s[1]]
    noise = [s for s in STREAM if not s[1]]
    real_survived = sum(1 for text, _ in real if tri.actionable(text))
    noise_dropped = sum(1 for text, _ in noise if not tri.actionable(text))

    recall = real_survived / len(real)
    drop_rate = noise_dropped / len(noise)
    smart_calls = len(gw.smart_calls) + tri.smart_calls

    print("==== ROOM 1 — TRIAGE GATE ====")
    print(f"  stream: {len(STREAM)} events ({len(noise)} noise / {len(real)} real)")
    print(f"  RECALL on real     : {real_survived}/{len(real)} = {recall:.3f}   [hard bar 1.000 — never drop a real event]")
    print(f"  noise-drop rate    : {noise_dropped}/{len(noise)} = {drop_rate:.3f}")
    print(f"  smart-model calls  : {smart_calls}   [cost spine: must be 0 — triage is free]")

    fails = []
    if recall != 1.0:
        missed = [text for text, _ in real if not tri.actionable(text)]
        fails.append(f"dropped real events (recall {recall:.3f}): {missed}")
    if smart_calls != 0:
        fails.append(f"triage touched the smart model ({smart_calls} calls) — cost spine broken")
    if drop_rate < 0.90:
        leaked = [text for text, _ in noise if tri.actionable(text)]
        fails.append(f"noise-drop {drop_rate:.3f} below 0.90 bar; leaked: {leaked}")

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; sys.exit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    main()
