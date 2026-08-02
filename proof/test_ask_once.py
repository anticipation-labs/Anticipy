#!/usr/bin/env python3
"""She may ask, but not over and over.

2026-07-31, from his real history:

  18:58:14  "Just checking Sharky's Diner opening hours. I'll text you when
             I have something solid."
  18:58:31  "Hey, I need the location for Sharky's Diner before I can check
             their hours."
  19:19     the same two again
  22:32     and again

The held-job path at least had the queue's own dedup behind it. The "ask"
branch had no guard whatever: it called notify_owner every single time
triage came back needing a detail — so the same missing detail was asked for
on every pass, and a redeploy or the pendant and phone both hearing him each
counted as a pass.

Every unprompted thing she says now goes through one rule, and the record it
consults is the backend's, not this process's.

Usage:  PYTHONPATH=. python3 proof/test_ask_once.py
"""
from __future__ import annotations

import json
import re
import sys
import types

import brain.anticipy_core as A
import brain.worker as W

PASS = FAIL = 0
SENT: list[str] = []
EVENTS: list[dict] = []      # what she has actually sent, as the backend holds it
JOBS: list[dict] = []


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))


class Resp:
    def __init__(self, items=None, rid="j1"):
        self.ok = True
        self._items = items or []
        self._rid = rid
    def json(self): return {"items": self._items, "id": self._rid}
    def raise_for_status(self): pass


def shared_get(url, **kw):
    """One fake for both modules — brain.worker and brain.anticipy_core import
    the SAME pb module, so assigning W.pb.get and then A.pb.get silently
    replaces the first with the second. That is how this test first "proved"
    the guard was broken when it was fine: every event query was answered with
    the job list. Honours the decision filter, as the backend does."""
    if "/events/" in url:
        filt = (kw.get("params") or {}).get("filter", "")
        m = re.search(r'decision="([^"]+)"', filt)
        return Resp([e for e in EVENTS if not m or e.get("decision") == m.group(1)])
    return Resp(list(JOBS))


assert W.pb is A.pb, "if these ever diverge, patch both"
W.pb.get = shared_get
W.pb.post = lambda url, **kw: Resp()


def brain(decision: str, goal: str, say: str):
    """A FRESH brain every time — a redeploy, or his phone and pendant both
    hearing him, look exactly like this."""
    class LLM:
        live = True
        def chat(self, system, user, **kw):
            if "decision" in system.lower() and "goal" in system.lower():
                return types.SimpleNamespace(text=json.dumps(
                    {"decision": decision, "goal": goal, "needs_confirmation": True,
                     "reason": "", "missing": ["which location"], "assumption": ""}))
            return types.SimpleNamespace(text=say)
    mem = types.SimpleNamespace(
        ingest=lambda *a, **k: {"commitment_id": None}, recall=lambda *a, **k: [],
        open_loops=lambda: [], close_from_speech=lambda *a, **k: [])
    b = A.Anticipy(memory=mem, llm=LLM())
    b.notify_owner = lambda m, channel="sms": SENT.append(m)
    return b


def hear_once(line: str, decision: str, goal: str, say: str):
    """One pass through the worker's hearing path, recording what went out
    exactly as the worker records it — the decision triage actually reached,
    not the one the test hoped for."""
    before = len(SENT)
    b = brain(decision, goal, say)
    out = b.hear(line, may_say=W.SPEAK_ONCE)
    if len(SENT) > before:
        EVENTS.append({"kind": "anticipy_says", "text": SENT[-1],
                       "decision": out["decision"].decision,
                       "goal": out["decision"].goal or ""})
    return out


SHARKY = "check Sharky's Diner opening hours"
ASK = "Hey, I need the location for Sharky's Diner before I can check their hours."

for _ in range(3):
    hear_once("what time does sharkys close", "ask", SHARKY, ASK)
check("the same missing detail is asked for once, not three times",
      len(SENT) == 1, f"{len(SENT)} texts: {SENT}")

# A genuinely different question must still reach him.
hear_once("cactus club sometime", "ask", "book a table at Cactus Club",
          "Which night did you want?")
check("a different question still reaches him", len(SENT) == 2, f"{SENT}")

# Asking again about the SAME thing, still quiet.
hear_once("sharkys hours?", "ask", SHARKY, ASK)
check("and still quiet on the first one afterwards", len(SENT) == 2, f"{SENT}")

# With no guard supplied at all she speaks — the guard is the caller's job and
# its absence must never make her mute.
before = len(SENT)
b = brain("ask", SHARKY, ASK)
b.hear("what time does sharkys close")
check("without a guard she still speaks", len(SENT) == before + 1)

# A broken guard must not silence her either.
before = len(SENT)
b = brain("ask", SHARKY, ASK)
b.hear("what time does sharkys close",
       may_say=lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
check("a guard that throws does not make her mute", len(SENT) == before + 1)

print(f"\nask once: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
