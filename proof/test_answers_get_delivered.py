#!/usr/bin/env python3
"""A question he asks must come back with an answer.

His Twilio history, three times over: "What's the weather in Mtl" (07-15 and
07-31), "What's the weather this Sunday" (07-17). Every one became a research
job. Not one of them ever came back to him. Nothing in the brain texted a
finished job's result — review_loops() only moved an in-RAM status, and the
places she spoke were all "want me to?", "which one?", "I need X" and the
clock. The answer sat on the job row forever.

Usage:  PYTHONPATH=. python3 proof/test_answers_get_delivered.py
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


class Resp:
    def __init__(self, items=None):
        self.ok = True
        self._items = items if items is not None else []
    def json(self): return {"items": self._items}


def run(jobs, events, voice="Montreal's 22 and clear today."):
    """Returns (texts sent, events posted)."""
    sent, posted = [], []
    W.REPORTED.clear()

    def fake_get(url, **kw):
        if "/jobs/" in url:
            return Resp(jobs)
        if "/events/" in url:
            # Honour the decision filter the way the backend does. A fake that
            # returns everything regardless of the filter proves nothing — it
            # is the same trap as a job fake with no "id", which silently
            # disabled the queue dedup and made a broken test look green.
            filt = (kw.get("params") or {}).get("filter", "")
            m = re.search(r'decision="([^"]+)"', filt)
            if m:
                return Resp([e for e in events if e.get("decision") == m.group(1)])
            return Resp(events)
        return Resp()

    W.pb.get = fake_get
    W.pb.post = lambda url, **kw: posted.append(kw.get("json") or {}) or Resp()
    anticipy = types.SimpleNamespace(
        owner_id="X",
        notify_owner=lambda m, channel="sms": (sent.append(m), {"sid": "SM1"})[1],
        _voice=lambda ctx: voice)
    W.report_finished_jobs(anticipy)
    return sent, posted


DONE = [{"id": "j1", "goal": "research weather in Montreal",
         "status": "done", "result": "Montreal: 22C, clear, light wind."}]

# --- the core failure ------------------------------------------------------
sent, posted = run(DONE, [])
check("a finished question is actually delivered", len(sent) == 1, f"{len(sent)} texts")
check("the delivery is recorded so a restart cannot repeat it",
      any(p.get("decision") == "done" and p.get("goal") == DONE[0]["goal"]
          for p in posted), f"posted: {posted}")

# --- restart safety --------------------------------------------------------
already = [{"kind": "anticipy_says", "goal": "research weather in Montreal",
            "decision": "done", "text": "Montreal: 22C, clear."}]
sent, _ = run(DONE, already)
check("after a restart the same answer is not sent again", not sent, f"{sent}")

# --- her earlier "want me to?" must NOT silence the answer -----------------
asked_first = [{"kind": "anticipy_says", "goal": "research weather in Montreal",
                "decision": "clock", "text": "Want me to look up Montreal weather?"}]
sent, _ = run(DONE, asked_first)
check("an earlier message about the same task does not swallow the answer",
      len(sent) == 1, f"{len(sent)} texts")

# --- failures are reported too --------------------------------------------
failed = [{"id": "j2", "goal": "research weather in Montreal",
           "status": "failed", "result": ""}]
sent, _ = run(failed, [], voice="Couldn't get the Montreal weather — want me to retry?")
check("a failure is told to him rather than swallowed", len(sent) == 1, f"{sent}")

# --- finished with nothing written down ------------------------------------
# This assertion used to say the opposite: that a done job with no result
# should stay quiet. That was wrong, and it was the worst possible place to be
# wrong — the browser fills `result` from the model's own done-claim, so a
# model that finishes without articulating one leaves it empty. His table
# would have been booked and he would never have learned it.
sent, _ = run([{"id": "j3", "goal": "Book dinner at Cactus Club",
                "status": "done", "result": ""}], [],
              voice="That's done — the Cactus Club booking went through.")
check("a task that finishes with nothing written down is still reported",
      len(sent) == 1, f"{sent}")

# --- in-flight work is not announced ---------------------------------------
sent, _ = run([], [])
check("nothing finished means nothing sent", not sent, f"{sent}")

print(f"\nanswers delivered: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
