#!/usr/bin/env python3
"""He must be able to call off anything she is holding — including a task
that is stopped waiting for information.

Production at 06:35 on 2026-08-02, both of his tasks blocked:

  needs_user  Book dinner at Cactus Club Park Royal for 2 people
  needs_user  Facilitate car insurance renewal   <- she invented this one

"No, I never said anything about car insurance" was the obvious thing for
him to send, and it would have done nothing at all. Cancelling resolved the
target from the PENDING list, which holds only tasks waiting on his yes; a
blocked task is not in it. So nothing would flip, and the model's drafted
"okay, I've dropped it" would go out anyway — a lie about the one task he
most wanted gone.

A blocked task is precisely the one nagging him. Calling off has to reach it.

Usage:  PYTHONPATH=. python3 proof/test_can_say_no.py
"""
from __future__ import annotations

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
          "result": "I need your first name, last name, email address, and phone number."}
INSURANCE = {"id": "insurance", "status": "needs_user", "params": "{}",
             "goal": "Facilitate car insurance renewal",
             "result": "Stopped before acting. I raised this on my own."}
HELD = {"id": "held", "status": "awaiting_confirm", "params": "{}",
        "goal": "Email Marcus the quarterly numbers", "result": ""}


class Resp:
    def __init__(self, items=None, single=None):
        self.ok = True
        self._items = items if items is not None else []
        self._single = single
    def json(self):
        return self._single if self._single is not None else {"items": self._items}


def build(jobs):
    flips = []

    def get(url, **kw):
        if "/jobs/records/" in url:                       # single fetch by id
            jid = url.rsplit("/", 1)[-1]
            hit = [j for j in jobs if j["id"] == jid]
            return Resp(single=hit[0]) if hit else Resp(single={})
        filt = (kw.get("params") or {}).get("filter", "")
        if 'status="needs_user"' in filt:
            return Resp([j for j in jobs if j["status"] == "needs_user"])
        if 'status="awaiting_confirm"' in filt:
            return Resp([j for j in jobs if j["status"] == "awaiting_confirm"])
        return Resp([])

    def patch(url, **kw):
        flips.append((url.rsplit("/", 1)[-1], (kw.get("json") or {}).get("status")))
        return Resp(single={})

    C.pb.get, C.pb.patch = get, patch
    C.pb.post = lambda *a, **k: Resp(single={})
    anticipy = types.SimpleNamespace(owner_id="X", backend_url="http://pb", llm=None,
                                     memory=types.SimpleNamespace(recall=lambda *a, **k: []))
    convo = C.Conversation(anticipy=anticipy, llm=None, transport=None)
    return convo, flips


# --- the live case: naming the invented task kills it ----------------------
convo, flips = build([CACTUS, INSURANCE])
convo._cancel("insurance", owner_text="no, I never said anything about car insurance")
check("he can call off a task that is blocked, not just one awaiting his yes",
      flips == [("insurance", "cancelled")], f"{flips}")

# --- and the one he actually wants is untouched -----------------------------
check("the booking he does want is left alone",
      not any(f[0] == "cactus" for f in flips), f"{flips}")

# --- a bare "no" with two things open must ask, not guess -------------------
convo, flips = build([CACTUS, INSURANCE])
out = convo._cancel(None, owner_text="no")
check("a bare no with two things open is ambiguous, not a guess",
      out == "ambiguous" and flips == [], f"{out!r} {flips}")

# --- and the list she offers contains the blocked ones ----------------------
convo, _ = build([CACTUS, INSURANCE])
q = convo._which_one(cancel=True)
check("the call-off list names the blocked tasks",
      "car insurance" in q and "Cactus" in q, q)
check("and it is numbered like every other choice she offers",
      "1)" in q and "2)" in q, q)

# --- with exactly one open thing, no is unambiguous -------------------------
convo, flips = build([INSURANCE])
convo._cancel(None, owner_text="no")
check("with one thing open a bare no still works",
      flips == [("insurance", "cancelled")], f"{flips}")

# --- held tasks still cancellable, as before --------------------------------
convo, flips = build([HELD])
convo._cancel(None, owner_text="forget it")
check("a task awaiting his yes is still cancellable",
      flips == [("held", "cancelled")], f"{flips}")

# --- nothing open, nothing flipped ------------------------------------------
convo, flips = build([])
convo._cancel(None, owner_text="no")
check("with nothing open nothing is flipped", flips == [], f"{flips}")

print(f"\ncan say no: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
