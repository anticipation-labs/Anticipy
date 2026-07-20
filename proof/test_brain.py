import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain.orchestrator import Brain

# The 15 examples Omar asked about, as raw transcript lines, with expected class.
CASES = [
    ("I'll send you the pitch deck after this call.", "act"),
    ("We should grab dinner sometime this week.", "act"),
    ("Ha, that movie was ridiculous, so bad it's good.", "ignore"),
    ("Remind me to email the landlord on Monday.", "act"),
    ("Can you call the clinic to reschedule my appointment?", "act"),
    ("Let's set up a meeting Thursday at 3pm.", "act"),
    ("Let me check pricing before I answer them.", "act"),
    ("The results should be in the portal by now.", "ignore"),
    ("I really should cancel the gym membership.", "act"),
    ("We're out of coffee again.", "act"),
    ("It's Sarah's birthday next week.", "ignore"),
    ("I'll share the contract with them today.", "act"),
    ("I'm thinking about a trip to Lisbon in the fall.", "ignore"),
    ("Tell them I'm running about ten minutes late.", "act"),
    ("Should I go with the blue one or the black one?", "ask"),
]


def main():
    brain = Brain()
    mode = brain.llm.chat("", "warmup").mode
    print(f"BRAIN MODE: {mode}\n")
    passed = 0
    for line, expected in CASES:
        d = brain.triage(line)
        ok = d.decision == expected
        passed += ok
        flag = "OK " if ok else "XX "
        conf = " [confirm]" if d.needs_confirmation else ""
        print(f"{flag}{d.decision:6} (exp {expected:6}) goal={str(d.goal):28}{conf}  <- {line}")
    print(f"\n{passed}/{len(CASES)} triaged as expected")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
