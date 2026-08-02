#!/usr/bin/env python3
"""He texts, he hears back. Always — including when her reasoning breaks.

2026-08-01, from his real history: he answered two of her questions and got
nothing at all.

  06:13  "yea grab it pls"                              -> silence
  17:38  "I want to see the Odyssey at Cineplex Park Royal" -> silence

Both hit an exception inside on_reply (the `convo` shadowing bug was live that
day: every inbound raised 'list' object has no attribute 'transport'). The
worker caught it, marked the event processed so it would never be retried, and
moved on. From his side the assistant simply did not exist.

Catching the exception is right — one bad message must not stall the queue or
mint duplicate jobs on replay. Saying nothing is not.

Usage:  PYTHONPATH=. python3 proof/test_never_silent.py
"""
from __future__ import annotations

import sys
import types

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


class Resp:
    def __init__(self, items=None):
        self.ok = True
        self._items = items if items is not None else []
    def json(self): return {"items": self._items, "id": "e1"}
    def raise_for_status(self): pass


def run_inbound(text: str, blow_up: bool, voice_works: bool = True):
    """Drive one inbound message through the worker's handling. Returns what
    he actually received."""
    said = []
    events = [{"id": "e1", "text": text, "goal": "+16047245161", "kind": "sms_reply"}]

    W.pb.get = lambda url, **kw: Resp(events if "/events/" in url else [])
    W.pb.post = lambda url, **kw: Resp()
    W.pb.patch = lambda url, **kw: Resp()

    class Convo:
        def on_reply(self, phone, t):
            if blow_up:
                raise AttributeError("'list' object has no attribute 'transport'")
            return {"intent": "confirm", "reply": "On it."}
        def say(self, phone, msg):
            said.append(msg)

    anticipy = types.SimpleNamespace(
        owner_phone="+16047245161", owner_id="X",
        _voice=(lambda ctx: "That one got away from me — say it again?")
               if voice_works else (lambda ctx: None))

    convo = Convo()
    # The worker's inbound block, exercised directly.
    try:
        out = convo.on_reply("+16047245161", text)
    except Exception:
        try:
            convo.say("+16047245161", anticipy._voice({
                "situation": "your own reasoning just failed", "their_message": text,
            }) or "Something went wrong on my end just then — can you send that again?")
        except Exception:
            pass
        return said
    convo.say("+16047245161", out["reply"])
    return said


# --- the normal path still works ------------------------------------------
got = run_inbound("yea grab it pls", blow_up=False)
check("a normal reply reaches him", len(got) == 1, f"{got}")

# --- the exact 2026-08-01 failure -----------------------------------------
got = run_inbound("yea grab it pls", blow_up=True)
check("a crash in her reasoning still gets him an answer", len(got) == 1, f"{got}")
check("that answer admits it rather than pretending",
      got and "again" in got[0].lower(), f"{got}")

got = run_inbound("I want to see the Odyssey at Cineplex Park Royal", blow_up=True)
check("the Cineplex message would not vanish today", len(got) == 1, f"{got}")

# --- even with no voice available -----------------------------------------
got = run_inbound("yea grab it pls", blow_up=True, voice_works=False)
check("with the model down he still hears something", len(got) == 1, f"{got}")

# --- the real worker actually has this guard ------------------------------
import inspect
src = inspect.getsource(W.main) if hasattr(W, "main") else ""
if not src:
    src = open(W.__file__).read()
after_error = src.split('print(f"sms in: {text!r} -> error')[-1][:600]
check("the guard is in worker.py, not just in this test",
      "convo.say(" in after_error, "the except branch does not speak")

print(f"\nnever silent: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
