#!/usr/bin/env python3
"""What a task is waiting for must survive the runner overwriting it.

The browser writes its own notes into a job's `result`, and the extension's
staleness bounce replaces that field wholesale. But `result` is also the ONLY
place the requirement lived — "I need your first name, last name, email
address, and phone number" — and it is what _answers_need() matches his reply
against. Trample it and no answer can ever be matched to that task again; the
booking is unrecoverable even by answering correctly a second time.

This is live right now: the fix that stops the bounce happening at all is in
extension/background.js, and until Omar reloads the extension the OLD code is
what runs against his real Cactus booking. So the requirement is now also
kept where the brain owns it and read back from there when the borrowed field
has been trampled.

Usage:  PYTHONPATH=. python3 proof/test_requirement_survives.py
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


NEED = "I need your first name, last name, email address, and phone number."
BOUNCE = "Still queued after 21 hours without running. Does it still stand?"


class Resp:
    ok = True
    def __init__(self, items=None):
        self._items = items if items is not None else []
    def json(self): return {"items": self._items}


def build(jobs):
    patched = []
    C.pb.get = lambda url, **kw: Resp(list(jobs))
    C.pb.patch = lambda url, **kw: patched.append((url.rsplit("/", 1)[-1],
                                                   kw.get("json") or {})) or Resp()
    C.pb.post = lambda *a, **k: Resp()
    anticipy = types.SimpleNamespace(owner_id="X", backend_url="http://pb", llm=None,
                                     memory=types.SimpleNamespace(recall=lambda *a, **k: []))
    return C.Conversation(anticipy=anticipy, llm=None, transport=None), patched


HIS_DETAILS = {"first_name": "Omar", "last_name": "Ebrahim",
               "email": "omar@example.com", "phone_number": "604 724 5161"}

# --- resuming stashes what it was waiting for -------------------------------
job = {"id": "cactus", "status": "needs_user", "params": "{}",
       "goal": "Book dinner at Cactus Club Park Royal", "result": NEED}
convo, patched = build([job])
convo._resume_stuck(HIS_DETAILS)
check("resuming the task keeps a copy of what it needed",
      patched and json.loads(patched[0][1]["params"]).get("needed", "").startswith("I need your first"),
      f"{patched}")

# --- after the runner tramples result, she still knows ----------------------
trampled = {"id": "cactus", "status": "needs_user",
            "params": json.dumps({"needed": NEED}),
            "goal": "Book dinner at Cactus Club Park Royal", "result": BOUNCE}
convo, _ = build([trampled])
blocked = convo._blocked()
# `needs` deliberately shows the runner's NEWEST note: a task that blocks
# again on something genuinely new must be able to say so. The requirement the
# brain established is carried alongside it, and that is what matching uses.
check("the requirement is still carried after result is overwritten",
      blocked and "first name" in blocked[0]["remembered_need"], f"{blocked}")

# --- and his answer can still be matched to it ------------------------------
convo, patched = build([trampled])
convo._resume_stuck(HIS_DETAILS)
check("so his details still restart the task he answered",
      [p[0] for p in patched] == ["cactus"], f"{patched}")

# --- without the kept copy, this is exactly what would have happened --------
lost = {"id": "cactus", "status": "needs_user", "params": "{}",
        "goal": "Book dinner at Cactus Club Park Royal", "result": BOUNCE}
convo, patched = build([lost, {"id": "other", "status": "needs_user",
                               "params": "{}", "goal": "something else",
                               "result": "needs a flight number"}])
convo._resume_stuck(HIS_DETAILS)
check("(and with the requirement truly gone it correctly resumes nothing)",
      patched == [], f"{patched}")

# --- a live result is still preferred over the stored copy ------------------
fresh = {"id": "cactus", "status": "needs_user",
         "params": json.dumps({"needed": "stale old requirement"}),
         "goal": "g", "result": "I need your date of birth to finish."}
convo, _ = build([fresh])
blocked = convo._blocked()
check("the runner's current words win over the remembered copy",
      "date of birth" in blocked[0]["needs"], f"{blocked}")

# --- the stash never overwrites an existing one -----------------------------
already = {"id": "cactus", "status": "needs_user",
           "params": json.dumps({"needed": NEED}), "goal": "g",
           "result": BOUNCE}
convo, patched = build([already])
convo._resume_stuck(HIS_DETAILS)
check("a bounce message never replaces the real remembered requirement",
      patched and json.loads(patched[0][1]["params"])["needed"] == NEED,
      f"{patched}")

print(f"\nrequirement survives: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
