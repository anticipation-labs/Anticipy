#!/usr/bin/env python3
"""A task he just unblocked must actually run — and a refused text must not
be recorded as spoken.

Three defects found by tracing "what if he answers hours later", each
confirmed by two independent skeptics before being touched.

1. extension/background.js measured staleness from `job.created`, which
   PocketBase makes immutable. His Cactus booking was created 21 hours before
   he would supply his details, and the limit is 12 — so the moment the brain
   requeued it, the extension would refuse to claim it, every time, forever.
   She had already said "I'll finish the booking now". Worse, the refusal
   OVERWROTE `result`, destroying the requirement text the brain matches an
   answer against, so answering again could never rescue it either. Worst of
   all it said "my browser was closed" — written by the browser, while
   running, at the moment it wrote it.

2. worker.py kept an in-RAM ASKED_ABOUT set, marked before every other check.
   It defeated need_already_asked(), the durable guard written precisely so a
   task blocking on a NEW requirement could be raised again.

3. All three places she speaks unprompted recorded "she said it" whether or
   not the send succeeded. notify_owner() swallows transport failures and
   returns None, so one refused text bought 24 hours of silence about that
   task — the dedup guard reads those records as proof she spoke.

Usage:  PYTHONPATH=. python3 proof/test_resume_actually_runs.py
"""
from __future__ import annotations

import re
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


# ---------------------------------------------------------------- extension
SRC = open("extension/background.js").read()
block = SRC[SRC.find("const STALE_HOURS"):SRC.find("const STALE_HOURS") + 1200]

check("staleness is measured from when it was last queued, not row creation",
      "Date.parse(job.updated || job.created" in block, block[:200])
check("the refusal no longer asserts the browser was closed",
      "my browser was closed" not in SRC, "the false cause is still there")
check("the refusal preserves the requirement text instead of overwriting it",
      "job.result" in block and "had ? had" in block.replace("(had ?", "had ?"),
      block[:600])


# ------------------------------------------------------------------- worker
class Resp:
    def __init__(self, items=None, ok=True):
        self.ok = ok
        self._items = items if items is not None else []
    def json(self): return {"items": self._items}


JOB = {"id": "j1", "status": "needs_user",
       "goal": "Book dinner at Cactus Club Park Royal for 2 people",
       "result": "I need your first name, last name, email address, and phone number."}


def run_ask(events, send_works=True):
    sent, posted = [], []

    def get(url, **kw):
        if "/jobs/" in url:
            return Resp([JOB])
        if "/events/" in url:
            filt = (kw.get("params") or {}).get("filter", "")
            m = re.search(r'decision="([^"]+)"', filt)
            return Resp([e for e in events if not m or e.get("decision") == m.group(1)])
        return Resp()

    W.pb.get = get
    W.pb.post = lambda url, **kw: posted.append(kw.get("json") or {}) or Resp()

    def notify(msg, channel="sms"):
        sent.append(msg)
        return {"sid": "SM1"} if send_works else None      # None == refused

    anticipy = types.SimpleNamespace(
        owner_id="X", notify_owner=notify,
        _voice=lambda ctx: "I'm setting up the Cactus booking — send me your "
                           "first name, last name, email and phone?")
    W.ask_about_stuck_jobs(anticipy, None)
    return sent, posted


# the in-RAM set is gone entirely
check("no in-memory set can mute her across a process",
      not hasattr(W, "ASKED_ABOUT"), "ASKED_ABOUT still exists")

# first ask goes out and is recorded
sent, posted = run_ask([])
check("a blocked task is raised", len(sent) == 1, f"{sent}")
check("and recorded once it has actually been sent",
      any(p.get("decision") == "needs_user" for p in posted), f"{posted}")

# asked before, same requirement -> quiet
told = [{"kind": "anticipy_says", "goal": JOB["goal"], "decision": "needs_user",
         "text": "I'm setting up the Cactus booking — send me your first name, "
                 "last name, email and phone?"}]
sent, _ = run_ask(told)
check("the same requirement is not asked twice", not sent, f"{sent}")

# the SECOND round: same task, a different requirement
JOB2 = dict(JOB, result="I need your date of birth to finish the reservation.")
_saved, JOB = JOB, JOB2
sent, _ = run_ask(told)
JOB = _saved
check("a NEW requirement on the same task is raised, twice-in-a-row or not",
      len(sent) == 1, f"{sent}")

# a refused send must not count as having spoken
sent, posted = run_ask([], send_works=False)
check("a refused text is attempted", len(sent) == 1, f"{sent}")
check("but is NOT recorded as something she said",
      not posted, f"recorded anyway: {posted}")

print(f"\nresume actually runs: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
