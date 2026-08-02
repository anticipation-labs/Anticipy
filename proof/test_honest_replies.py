#!/usr/bin/env python3
"""She may never claim progress she has not made.

2026-08-02, live: she asked Omar for his first name, last name, email and
phone to finish the Cactus Club booking. He replied "Do it". She answered
"Got it. I'll finish up that booking now." — and then did nothing, because he
had supplied nothing. The task stayed blocked and he had no idea.

The guard is in code, not in the prompt: if nothing was learned, resumed or
acted on, and something is still blocked, her reply is replaced with what is
actually missing. These tests use a model that ALWAYS drafts a false claim, so
they test the enforcement rather than the model's good manners.

Usage:  PYTHONPATH=. python3 proof/test_honest_replies.py
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


BLOCKED = [{"id": "job1",
            "goal": "Book dinner at Cactus Club Park Royal for 2 people",
            "needs": "I need your first name, last name, email address, and "
                     "phone number to complete the reservation."}]

LIE = "Got it. I'll finish up that booking now."


class Resp:
    ok = True
    def __init__(self, items=None): self._items = items or []
    def json(self): return {"items": self._items}


class DraftsALie:
    """Classifies however the test says, and always drafts the false claim."""
    live = True
    def __init__(self, intent): self.intent = intent
    def chat(self, system, user, **kw):
        if "Anticipy" in system and "intent" in system:
            return types.SimpleNamespace(text=json.dumps(
                {"intent": self.intent, "pending_id": None, "changes": None,
                 "reply": LIE}))
        return types.SimpleNamespace(text=LIE)   # _voice, if it were used


def build(intent: str, learns: dict | None = None, blocked=BLOCKED):
    C.pb.get = lambda url, **kw: Resp()
    C.pb.post = lambda *a, **k: Resp()
    C.pb.patch = lambda *a, **k: Resp()
    llm = DraftsALie(intent)
    spoken = []
    anticipy = types.SimpleNamespace(
        owner_id="X", backend_url="http://pb",
        memory=types.SimpleNamespace(recall=lambda *a, **k: []),
        hear=lambda *a, **k: spoken.append(a),
        _voice=lambda ctx: None)      # no live voice: exercise the fallback
    convo = C.Conversation(anticipy=anticipy, llm=llm, transport=None)
    convo._pending = lambda: []
    convo._blocked = lambda: blocked
    convo._remember_about_owner = lambda t: dict(learns or {})
    convo._resume_stuck = lambda: ("job1" if learns else None)
    return convo


def reply_of(out) -> str:
    return (out.get("reply") or out.get("say") or "")


# --- nothing supplied: every action-shaped intent must own up ---------------
for intent, text in [("answer", "Do it"), ("confirm", "go ahead please"),
                     ("modify", "just get on with it")]:
    out = build(intent).on_reply("+1", text)
    r = reply_of(out)
    check(f"{intent!r} with nothing supplied does not claim progress",
          LIE not in r and "still" in r.lower(), f"said: {r!r}")

# --- he actually answers: she must NOT be muzzled ---------------------------
out = build("answer", learns={"name": "Omar Ebrahim"}).on_reply(
    "+1", "Omar Ebrahim, omar@example.com")
check("a real answer still gets the proceeding reply",
      LIE in reply_of(out), f"said: {reply_of(out)!r}")

# --- nothing blocked: ordinary conversation is untouched --------------------
out = build("confirm", blocked=[]).on_reply("+1", "yes")
check("with nothing blocked her reply is left alone",
      LIE in reply_of(out), f"said: {reply_of(out)!r}")

# --- declining is not an action claim; leave it be --------------------------
out = build("decline").on_reply("+1", "actually forget it")
check("declining is not rewritten into a demand for information",
      "still" not in reply_of(out).lower(), f"said: {reply_of(out)!r}")

# --- the missing thing is actually named -----------------------------------
out = build("answer").on_reply("+1", "Do it")
check("she names what is missing, not just that something is",
      "first name" in reply_of(out).lower(), f"said: {reply_of(out)!r}")

print(f"\nhonest replies: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
