#!/usr/bin/env python3
"""When his browser is not there, she says so instead of going quiet.

The likely shape of this morning: he is away from his desk, replies to her
question by text, the booking resumes to `queued` — and then waits for the
Chrome extension to claim it. If his laptop is shut, nothing ever does. She
had already said "I'll finish the booking now", and that is where it ends.

Nothing in the brain had ever asked whether his browser was reachable. It was
checked only by the standing proof script, never by her.

Usage:  PYTHONPATH=. python3 proof/test_says_when_it_cannot_run.py
"""
from __future__ import annotations

import re
import sys
import types
from datetime import datetime, timedelta, timezone

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


def stamp(seconds_ago: int) -> str:
    return (datetime.now(timezone.utc)
            - timedelta(seconds=seconds_ago)).strftime("%Y-%m-%d %H:%M:%S.000Z")


JOB = {"id": "j1", "status": "queued", "params": "{}",
       "goal": "Book dinner at Cactus Club Park Royal for 2 people"}


class Resp:
    def __init__(self, items=None, ok=True):
        self.ok = ok
        self._items = items if items is not None else []
    def json(self): return {"items": self._items}


def run(agents, jobs, events=None, hour=14):
    sent, posted = [], []

    def get(url, **kw):
        if "/agents/" in url:
            return Resp(agents)
        if "/jobs/" in url:
            return Resp(jobs)
        if "/events/" in url:
            filt = (kw.get("params") or {}).get("filter", "")
            m = re.search(r'decision="([^"]+)"', filt)
            evs = events or []
            return Resp([e for e in evs if not m or e.get("decision") == m.group(1)])
        return Resp()

    W.pb.get = get
    W.pb.post = lambda url, **kw: posted.append(kw.get("json") or {}) or Resp()
    anticipy = types.SimpleNamespace(
        owner_id="X", notify_owner=lambda m, channel="sms": sent.append(m),
        _voice=lambda ctx: "I'm ready to finish the Cactus booking — just need "
                           "your Chrome open and it'll go.")

    # Freeze the hour so quiet-hours behaviour is testable rather than
    # dependent on when the suite happens to run.
    real_dt = W.datetime
    class FrozenDT(real_dt):
        @classmethod
        def now(cls, tz=None):
            base = real_dt.now(tz)
            # ONLY the owner-local clock is frozen. Freezing every now() also
            # skewed the browser-liveness age by however far the hour moved,
            # so this suite passed or failed depending on the time of day it
            # was run — which is the whole trap it was written to avoid.
            return base.replace(hour=hour) if tz is W.CLOCK_TZ else base
    W.datetime = FrozenDT
    try:
        W.report_stalled_work(anticipy)
    finally:
        W.datetime = real_dt
    return sent, posted


LIVE = [{"id": "a", "paired": True, "last_seen": stamp(3)}]
DEAD = [{"id": "a", "paired": True, "last_seen": stamp(3600)}]

# --- the real case: browser shut, work waiting -----------------------------
sent, posted = run(DEAD, [JOB])
check("she tells him the work cannot start", len(sent) == 1, f"{sent}")
check("and names the task", sent and "Cactus" in sent[0], f"{sent}")
check("recorded durably so a restart does not repeat it",
      any(p.get("decision") == "stalled" for p in posted), f"{posted}")

# --- browser is there: she stays out of the way ----------------------------
sent, _ = run(LIVE, [JOB])
check("with his browser open she says nothing", not sent, f"{sent}")

# --- already told him once --------------------------------------------------
told = [{"kind": "anticipy_says", "goal": JOB["goal"], "decision": "stalled",
         "text": "..."}]
sent, _ = run(DEAD, [JOB], events=told)
check("she does not repeat it", not sent, f"{sent}")

# --- nothing queued, nothing to say ----------------------------------------
sent, _ = run(DEAD, [])
check("with nothing waiting she says nothing", not sent, f"{sent}")

# --- quiet hours ------------------------------------------------------------
sent, _ = run(DEAD, [JOB], hour=3)
check("she does not wake him at 3am for this", not sent, f"{sent}")
sent, _ = run(DEAD, [JOB], hour=23)
check("nor at 11pm", not sent, f"{sent}")

# --- never invent bad news --------------------------------------------------
def boom(*a, **k): raise RuntimeError("backend down")
W.pb.get = boom
check("if she cannot tell, she assumes the browser is fine",
      W.browser_reachable() is True)

W.pb.get = lambda url, **kw: Resp(ok=False)
check("a failed lookup is not treated as an absent browser",
      W.browser_reachable() is True)

print(f"\nsays when it cannot run: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
