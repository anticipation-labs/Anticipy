#!/usr/bin/env python3
"""His answer must restart the task that asked for it — even when more than
one task is blocked.

This is the state production was actually in at 06:00 on 2026-08-02, waiting
for him to wake up:

  needs_user  Book dinner at Cactus Club Park Royal for 2 people
              "I need your first name, last name, email address, and phone
               number to complete the reservation."
  needs_user  Facilitate car insurance renewal
              "Stopped before acting. I raised this on my own and I cannot
               point to anything you said about car insurance."

The resume rule was "only when exactly one thing is blocked, otherwise do
nothing". It reads as caution and is really a trap: two blocked tasks meant
his details would be remembered, NOTHING would resume, and — because
something WAS learned — the honesty guard would not fire either, so she would
still have said "Perfect, I'll finish the booking now" and then sat there.

Matching his answer against what each task said it needed is the honest
version of not guessing.

Usage:  PYTHONPATH=. python3 proof/test_resume_the_right_one.py
"""
from __future__ import annotations

import json
import sys
import types

import brain.conversation as C

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))


CACTUS = {"id": "cactus", "status": "needs_user", "params": "{}",
          "goal": "Book dinner at Cactus Club Park Royal for 2 people",
          "result": "I need your first name, last name, email address, and "
                    "phone number to complete the reservation."}
INSURANCE = {"id": "insurance", "status": "needs_user", "params": "{}",
             "goal": "Facilitate car insurance renewal",
             "result": "Stopped before acting. I raised this on my own and I "
                       "cannot point to anything you said about car insurance."}
GYM = {"id": "gym", "status": "needs_user", "params": "{}",
       "goal": "Sign up at the climbing gym",
       "result": "I need your date of birth to finish the waiver."}


class Resp:
    def __init__(self, items=None):
        self.ok = True
        self._items = items if items is not None else []
    def json(self): return {"items": self._items}


def run(jobs, learned):
    """Returns (resumed marker, ids actually re-queued)."""
    requeued = []
    C.pb.get = lambda url, **kw: Resp(list(jobs))
    def patch(url, **kw):
        requeued.append(url.rsplit("/", 1)[-1])
        return Resp()
    C.pb.patch = patch
    anticipy = types.SimpleNamespace(owner_id="X", backend_url="http://pb", llm=None,
                                     memory=types.SimpleNamespace(recall=lambda *a, **k: []))
    convo = C.Conversation(anticipy=anticipy, llm=None, transport=None)
    return convo._resume_stuck(learned), requeued


HIS_DETAILS = {"first_name": "Omar", "last_name": "Ebrahim",
               "email": "omar@example.com", "phone_number": "604 724 5161"}

# --- the exact production state ------------------------------------------
marker, requeued = run([CACTUS, INSURANCE], HIS_DETAILS)
check("his details restart the booking that asked for them",
      requeued == ["cactus"], f"re-queued {requeued}")
check("and it reports that something moved", bool(marker), f"{marker!r}")
check("the task he never asked for is left alone",
      "insurance" not in requeued, f"{requeued}")

# --- an answer that fits nothing must move nothing -------------------------
marker, requeued = run([CACTUS, INSURANCE], {"favourite_colour": "green"})
check("an unrelated fact restarts nothing", requeued == [], f"{requeued}")
check("and honestly reports no progress", marker is None, f"{marker!r}")

# --- two blocked tasks, both satisfied by one message ----------------------
marker, requeued = run([CACTUS, GYM],
                       dict(HIS_DETAILS, date_of_birth="1995-03-14"))
check("one message can unblock both tasks it answered",
      sorted(requeued) == ["cactus", "gym"], f"{requeued}")

# --- the head-word match: "phone_number" against a task saying "phone" -----
PHONE_ONLY = {"id": "p", "status": "needs_user", "params": "{}", "goal": "g",
              "result": "I just need a phone to put on the booking."}
_, requeued = run([PHONE_ONLY, INSURANCE], {"phone_number": "604 724 5161"})
check("'phone number' answers a task that asked for a 'phone'",
      requeued == ["p"], f"{requeued}")

# --- the long-standing single-task behaviour is preserved ------------------
VAGUE = {"id": "v", "status": "needs_user", "params": "{}", "goal": "g",
         "result": "Blocked — the site wants something I don't have."}
_, requeued = run([VAGUE], {"membership_number": "44821"})
check("with only one thing waiting she still resumes it",
      requeued == ["v"], f"{requeued}")

# --- nothing learned, nothing resumed --------------------------------------
_, requeued = run([VAGUE], {})
check("learning nothing resumes nothing", requeued == [], f"{requeued}")

# --- the re-queued job carries his authorization ---------------------------
bodies = []
C.pb.get = lambda url, **kw: Resp([CACTUS])
C.pb.patch = lambda url, **kw: bodies.append(kw.get("json") or {}) or Resp()
anticipy = types.SimpleNamespace(owner_id="X", backend_url="http://pb", llm=None,
                                 memory=types.SimpleNamespace(recall=lambda *a, **k: []))
C.Conversation(anticipy=anticipy, llm=None, transport=None)._resume_stuck(HIS_DETAILS)
check("the resumed task is queued and authorized",
      bodies and bodies[0].get("status") == "queued"
      and json.loads(bodies[0].get("params") or "{}").get("authorized") is True,
      f"{bodies}")

print(f"\nresume the right one: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
