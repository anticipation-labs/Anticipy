#!/usr/bin/env python3
"""When she asks him to choose, he must be able to choose.

2026-07-13, from his real history: she asked "Which one did you mean?
- Find a well-rated dinner recipe  - Check ingredients", he replied "2", and
nothing happened. Two faults, one deadlock:

  * the options were never numbered, so "2" referred to nothing;
  * _references demands a shared 4-letter word between his text and the job,
    and "2" has none — so the release came back "ambiguous" and she asked the
    same question again.

She asks him to pick, then refuses every natural way of picking. The guard
itself is right: with several things pending, a bare "yes" must not release
one at random. But a position IS a name, relative to the list she offered.

Usage:  PYTHONPATH=. python3 proof/test_pick_by_number.py
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


PENDING = [
    {"id": "jobA", "goal": "Find a well-rated dinner recipe",
     "params": "{}", "status": "awaiting_confirm"},
    {"id": "jobB", "goal": "Check ingredients for the recipe",
     "params": "{}", "status": "awaiting_confirm"},
]


class Resp:
    ok = True
    def __init__(self, items=None): self._items = items or []
    def json(self): return {"items": self._items}


def build(thread_events=None):
    C.pb.get = lambda url, **kw: Resp(thread_events or [])
    C.pb.post = lambda *a, **k: Resp()
    C.pb.patch = lambda *a, **k: Resp()
    anticipy = types.SimpleNamespace(
        owner_id="X", backend_url="http://pb", llm=None,
        memory=types.SimpleNamespace(recall=lambda *a, **k: []))
    convo = C.Conversation(anticipy=anticipy, llm=None, transport=None)
    convo._pending = lambda: PENDING
    convo._blocked = lambda: []
    return convo


# --- she numbers the options now -------------------------------------------
convo = build()
q = convo._which_one()
check("the options are numbered", "1)" in q and "2)" in q, q)
check("both goals are named", "dinner recipe" in q and "ingredients" in q, q)

# --- a digit resolves to the right job -------------------------------------
convo = build()
convo._which_one()                       # she asks
check("'2' picks the second thing she offered",
      convo._choice_from_position("2") == "jobB",
      f"got {convo._choice_from_position('2')!r}")
check("'1' picks the first", convo._choice_from_position("1") == "jobA")

# --- words work as well as digits ------------------------------------------
convo = build()
convo._which_one()
check("'the second one' works too",
      convo._choice_from_position("the second one") == "jobB",
      f"got {convo._choice_from_position('the second one')!r}")
check("'first' works too", convo._choice_from_position("first") == "jobA")

# --- it must NOT fire on ordinary sentences --------------------------------
convo = build()
convo._which_one()
for text in ["yes go ahead", "book the dinner recipe one please",
             "actually forget it", "I'll be there at 2 pm tomorrow with Sam"]:
    check(f"{text!r} is not treated as a position",
          convo._choice_from_position(text) is None,
          f"got {convo._choice_from_position(text)!r}")

# --- out of range is refused, not guessed ----------------------------------
convo = build()
convo._which_one()
check("a number past the end picks nothing",
      convo._choice_from_position("7") is None)

# --- after a restart it recovers from her own numbered question ------------
asked = [{"kind": "anticipy_says",
          "text": "Just to be sure — which one should I go ahead with: "
                  "1) Find a well-rated dinner recipe, 2) Check ingredients "
                  "for the recipe?"}]
convo = build(thread_events=asked)       # fresh object: nothing cached
check("a redeploy does not lose which list she offered",
      convo._choice_from_position("2") == "jobB",
      f"got {convo._choice_from_position('2')!r}")

# --- the guard that started all this is still intact ------------------------
convo = build()
job = {"goal": "Find a well-rated dinner recipe", "params": "{}"}
check("a bare yes still names nothing", not convo._references("yes", job))
check("naming the topic still counts",
      convo._references("go ahead with the dinner recipe", job))

print(f"\npick by number: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
