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


def run_inbound(text: str, blow_up: bool, voice_works: bool = True,
                kind: str = "sms_reply"):
    """Drive one inbound message through the worker's REAL handling.

    This used to re-type the worker's inbound block here and then grep
    worker.py for a `print` to check the real code still had the guard -- a test
    of a copy plus a test of a string, which is why the copy was free to drift.
    handle_inbound() is now the function main() calls, so this exercises
    production.
    """
    said = []
    posted = []
    ev = {"id": "e1", "text": text, "goal": "+16047245161", "kind": kind,
          "owner_ref": "ref1"}
    if kind == "app_reply":
        ev["goal"] = ""

    W.pb.get = lambda url, **kw: Resp([ev] if "/events/" in url else [])
    W.pb.post = lambda url, **kw: Resp()
    W.pb.patch = lambda url, **kw: Resp()
    W.post_event = lambda kind_, text_, **kw: posted.append(text_)

    class Convo:
        """Faithful to the collaborator handle_inbound actually gets.

        The real Conversation.say() records the turn but SKIPS the transport
        while reply_in_app() is open (verified: transport sends do not advance
        inside the block), because the caller delivers that reply on the channel
        the answer came in on. A stub that texts anyway reports a double
        delivery that production does not have.
        """

        def __init__(self):
            self.suppressed = False

        def on_reply(self, phone, t):
            if blow_up:
                raise AttributeError("'list' object has no attribute 'transport'")
            return {"intent": "confirm", "reply": "On it."}

        def say(self, phone, msg):
            if not self.suppressed:
                said.append(msg)

        def reply_in_app(self):
            import contextlib

            @contextlib.contextmanager
            def cm():
                self.suppressed = True
                try:
                    yield
                finally:
                    self.suppressed = False
            return cm()

    anticipy = types.SimpleNamespace(
        owner_phone="+16047245161", owner_ref="ref1", owner_id="X",
        _voice=(lambda ctx: "That one got away from me — say it again?")
               if voice_works else (lambda ctx: None))

    W.handle_inbound(ev, Convo(), anticipy)
    # What he received, by either route: a text, or a row the app renders.
    return said + posted


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

# --- the app lane must not reintroduce the silence in a new place ----------
got = run_inbound("7pm works", blow_up=True, kind="app_reply")
check("a crash on an in-app answer still answers him", len(got) == 1, f"{got}")
check("...and it lands where the app can render it",
      got and "again" in got[0].lower(), f"{got}")

# --- the function under test is the one production calls -------------------
# The old version of this check grepped worker.py for a print string, which
# tested a string. What matters is that main() still delegates here: re-inlining
# the loop would leave handle_inbound orphaned and every test above green while
# production ran something else.
import inspect
main_src = inspect.getsource(W.main)
check("main() delegates to the handler these tests drive",
      "handle_inbound(" in main_src,
      "main() no longer calls handle_inbound — these tests now prove nothing")
check("both channels are read into that one handler",
      'fetch_unprocessed("sms_reply"' in main_src
      and 'fetch_unprocessed("app_reply"' in main_src,
      "one of the two answer channels is not being polled")

print(f"\nnever silent: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
