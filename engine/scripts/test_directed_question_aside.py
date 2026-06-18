"""LOCK: a question/request addressed to a NAMED third party is silenced DETERMINISTICALLY.

Regression for the intermittent cardinal-sin floor breach the adversarial verification caught:
the mega-eval line "Jordan, can you pull the freight numbers for the call?" (a question to a third
party — not the owner's task) slipped past the interrogative-aside guards (which only caught PAST/
PERFECT auxiliaries like "did you ...") and reached the MOAT model, which flickered it into an ASK card
in ~half of real-model runs (safety_mega_eval BREACHES: 1, intermittently). The deterministic guard now
silences "Name, can you ...?" so the model's coin-flip can never breach.

Deterministic — pure regex guard, zero model calls. Asserts the breach line + sibling third-party
requests are silenced, AND that real assistant-tasks / money lines are NEVER over-silenced (the guard
must not become a new task-dropping bug).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anticipy_engine.core.control_core import _is_interrogative_aside  # noqa: E402


SILENCE = [  # questions to a NAMED third party -> their task, never the owner's
    "Jordan, can you pull the freight numbers for the call?",   # the exact mega-eval breach line
    "Mom, could you grab milk?",
    "Maya, will you email the board the update?",
    "Sam, can you forward the contract?",
    "did you remind Jenny to send the slides",                  # existing past-aux aside (must still hold)
    # 20-life regressions: no-comma name, and owner-beneficiary "my X" that is STILL the named person's task
    "Sam can you take the on-call handoff Thursday?",           # no vocative comma (real speech drops it)
    "Marcus, can you pick up my prescription at Walgreens?",    # "my prescription" is the OBJECT of Marcus's errand
    "Tomas, can you grab milk and my prescription on your way home?",
    "Sarah, can you send me the deck?",                         # a question to Sarah, not a task for the assistant
    "Marcus, can you cover the first half of my Friday shift?",
]

KEEP = [  # must NOT be silenced — real assistant tasks / money / fillers / weekday openers
    "can you remind me to call mom at 3?",        # request to the assistant (no name vocative) -> keep
    "Well, can you check the weather",            # sentence-opener filler, not a name -> keep
    "Anticipy, can you check the weather",        # the assistant by name -> keep
    "Today can you book the dentist for me",      # weekday/time opener, not a name -> keep
    "Pay the $1,450 rent",                         # money line -> must reach the money wall, never silenced
    "remind me to send Maya the email before Friday",  # owner task that names a person -> keep
    "buy the standing desk off Amazon",            # shopping line -> keep
]


def main():
    fails = []
    for t in SILENCE:
        if not _is_interrogative_aside(t):
            fails.append(f"NOT silenced (breach risk): {t!r}")
    for t in KEEP:
        if _is_interrogative_aside(t):
            fails.append(f"OVER-silenced (task-drop risk): {t!r}")
    if fails:
        for f in fails:
            print("FAIL:", f)
        raise SystemExit(1)
    print("PASS directed_question_aside: third-party questions silenced; assistant tasks/money kept")


if __name__ == "__main__":
    main()
