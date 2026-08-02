#!/usr/bin/env python3
"""Say the same thing three times, get asked once.

From his real Twilio history, 2026-08-01: six separate texts about ONE email
to Marcus, over half an hour. The queue had deduped identical goals since the
five-copies incident — but hear() texted him on every pass regardless, because
the dedup lived inside _queue_job and its result was never consulted before
notifying. One task, six asks.

Usage:  PYTHONPATH=. python3 proof/test_one_ask_per_task.py
"""
from __future__ import annotations

import json
import sys
import types

import brain.anticipy_core as A

PASS = FAIL = 0
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


def fake_post(url, **kw):
    body = kw.get("json") or {}
    rid = f"job{len(JOBS) + 1}"
    JOBS.append({"id": rid, "goal": body.get("goal", ""),
                 "status": body.get("status", "")})
    return Resp(rid=rid)


A.pb.get = lambda url, **kw: Resp(list(JOBS))
A.pb.post = fake_post


def brain_for(goal: str, say: str, sent: list):
    """A brain whose triage always lands on `goal` — the utterances differ,
    the understood intent does not, which is exactly the real case."""
    class LLM:
        live = True
        def chat(self, system, user, **kw):
            if "JSON" in system and "decision" in system:
                return types.SimpleNamespace(text=json.dumps(
                    {"decision": "act", "goal": goal, "needs_confirmation": True,
                     "reason": "", "missing": [], "assumption": ""}))
            return types.SimpleNamespace(text=say)

    mem = types.SimpleNamespace(
        ingest=lambda *a, **k: {"commitment_id": None},
        recall=lambda *a, **k: [], open_loops=lambda: [],
        close_from_speech=lambda *a, **k: [])
    b = A.Anticipy(memory=mem, llm=LLM())
    b.notify_owner = lambda m, channel="sms": sent.append(m)
    return b


sent: list[str] = []
MARCUS = "Draft email to Marcus with the quarterly numbers for tomorrow"
# Each utterance goes through a FRESH brain: this is what a redeploy, or the
# pendant and the phone hearing him separately, actually looks like. Nothing
# may depend on one process having remembered the earlier pass.
for line in ["I need to send Marcus the quarterly numbers tomorrow",
             "don't forget the quarterly numbers for Marcus tomorrow",
             "the Marcus quarterly numbers email, for tomorrow"]:
    brain_for(MARCUS, "I've got that email to Marcus ready. Send it?", sent).hear(line)

check("three ways of saying it queue one task", len(JOBS) == 1, f"{len(JOBS)} jobs")
check("three ways of saying it earn one text", len(sent) == 1, f"{len(sent)} texts")

brain_for("Book a dentist appointment for next week",
          "Want me to book the dentist?", sent).hear("I should book the dentist for next week")
check("a genuinely different task still reaches him",
      len(JOBS) == 2 and len(sent) == 2, f"{len(JOBS)} jobs, {len(sent)} texts")

print(f"\none ask per task: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
