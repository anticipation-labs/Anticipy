#!/usr/bin/env python3
"""When a task stops for a NEW reason, she says so.

The stuck-job guard added earlier on 2026-08-02 keyed on the task, for a day:
once she had asked about a booking she would not raise that booking again.
That is right for the case it was built for — a redeploy must not make her
re-send the same request — and wrong on the second round.

If he answers part of what a form wants, the task resumes, the browser gets
further, and stops on something else. A task-keyed guard keeps her quiet
about the new thing for the rest of the day, and the task dies in silence:
exactly the failure the stuck-job ask exists to prevent.

Her own wording cannot be used to tell these apart — it is generated fresh
every time, which is how the first version of this guard failed. The
BLOCKER can: it is the browser's own words about what it needs.

Usage:  PYTHONPATH=. python3 proof/test_asks_again_when_the_need_changes.py
"""
from __future__ import annotations

import sys

import brain.worker as W

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))


GOAL = "Book dinner at Cactus Club Park Royal for 2 people"
FIRST_NEED = ("I need your first name, last name, email address, and phone "
              "number to complete the reservation.")
# What she actually sent about it — note the wording is nothing like the
# blocker, which is why comparing her text to her text never worked.
SHE_SAID = ("Hey, I'm setting up that Cactus Club reservation now. Can you "
            "send over your first name, last name, email and phone?")
NEW_NEED = "I need your date of birth to finish the reservation."
OTHER_TASK_NEED = "I need the flight number before I can check you in."


class Resp:
    ok = True
    def __init__(self, items=None): self._items = items or []
    def json(self): return {"items": self._items}


def with_history(events):
    W.pb.get = lambda url, **kw: Resp(events)


HISTORY = [{"kind": "anticipy_says", "goal": GOAL, "decision": "needs_user",
            "text": SHE_SAID}]

with_history(HISTORY)
check("she does not ask twice for the same thing",
      W.need_already_asked(GOAL, FIRST_NEED) is True)

check("but a NEW thing the same task needs does get asked",
      W.need_already_asked(GOAL, NEW_NEED) is False,
      "she would have gone silent and the booking would have died")

check("a different task is never covered by this one",
      W.need_already_asked("Check in for the Lisbon flight", FIRST_NEED) is False)

with_history([])
check("with nothing sent yet she asks", W.need_already_asked(GOAL, FIRST_NEED) is False)

with_history(HISTORY)
check("an empty blocker is not treated as answered",
      W.need_already_asked(GOAL, "") is False)
check("an empty goal is not treated as answered",
      W.need_already_asked("", FIRST_NEED) is False)

# Rewording of the SAME requirement must still count as asked — this is the
# case that made the previous, text-similarity version useless.
REWORDED = ("Before I can finish the reservation I need your first name, "
            "last name, an email address and a phone number.")
with_history(HISTORY)
check("the same requirement worded differently still counts as asked",
      W.need_already_asked(GOAL, REWORDED) is True)

# A blocker that shares only filler words must NOT count as covered.
with_history(HISTORY)
check("sharing only filler words does not count as asked",
      W.need_already_asked(GOAL, OTHER_TASK_NEED) is False)

# A broken backend must not silence her.
def boom(*a, **k): raise RuntimeError("backend down")
W.pb.get = boom
check("if the check itself fails she still speaks",
      W.need_already_asked(GOAL, FIRST_NEED) is False)

print(f"\nasks again when the need changes: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
