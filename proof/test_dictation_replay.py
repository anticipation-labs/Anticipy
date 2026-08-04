#!/usr/bin/env python3
"""The 2026-08-04 false fires, replayed — and this time she stays quiet.

That day the owner dictated messages to another AI through voice-to-text
(Wispr Flow) while his pendant listened. The transcript reached triage as a
stream of fluent instruction-prose, triage read requests in it — which is
its job — and he watched "On it" fire about messages that were never spoken
to her (roadmap §7.1, brief 02).

The verbatim transcript of that session is not preserved in this repo, so
the lines below are reconstructed to the incident's exact shape: long
fluent dictation runs instructing another AI about this very product,
interleaved with the short trailing fragments a dictation session produces.
The scripted model replays the LIVE failure honestly: it stays as eager as
the real one was (act, with goals, on nearly every line), it misclassifies
one long run as assistant-directed, and it omits the addressee entirely on
another — so the replay passes only if the deterministic floor, the model's
classification, and the ambient lane hold up together.

DONE means: across the whole dictation session, zero texts, zero held
jobs, zero "On it" — and the one line actually spoken TO her afterwards
still acts, so the fix is a lane, not a mute button.

Usage:  PYTHONPATH=. python3 proof/test_dictation_replay.py
"""
from __future__ import annotations

import json
import sys
import types

from brain.anticipy_core import Anticipy

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))


class ScriptedLLM:
    live = True

    def __init__(self, triage_responses: list[dict]):
        self.queue = list(triage_responses)
        self.triage_prompts: list[str] = []

    def chat(self, system, user, **kw):
        if '"decision"' in (system or ""):
            self.triage_prompts.append(user)
            return types.SimpleNamespace(text=json.dumps(self.queue.pop(0)))
        return types.SimpleNamespace(text="Okay — should I go ahead?")


class Offline(Anticipy):
    def __init__(self, llm):
        mem = types.SimpleNamespace(
            ingest=lambda *a, **k: {"commitment_id": None},
            recall=lambda *a, **k: [],
            open_loops=lambda: [],
            close_from_speech=lambda *a, **k: [])
        super().__init__(memory=mem, llm=llm, backend_url="http://127.0.0.1:1")
        self.queued: list[dict] = []
        self.texts: list[str] = []

    def _queue_job(self, goal, params, hold=False, explicit=False):
        self.queued.append({"goal": goal, "params": params, "hold": hold})
        return f"job{len(self.queued)}"

    def notify_owner(self, message, channel="sms"):
        self.texts.append(message)
        return {"sent": True}

    def _same_pending(self, goal):
        return None


# The dictation session, in the order he spoke it. Each entry: the line, and
# what the eager live-style model returns for it.
SESSION = [
    # A long run the model MISCLASSIFIES as a direct ask — the deterministic
    # floor must catch it, because on 2026-08-04 nothing did.
    ("Okay so in the message to the team make sure you mention that the "
     "extension kept opening tabs on top of me all night, and please ask "
     "whether we can move the research jobs off my browser entirely, and "
     "then add a line about the store listing review timeline.",
     {"decision": "act",
      "goal": "draft and send a message to the team about the extension",
      "addressee": "assistant", "reason": "owner wants a message sent"}),
    # A long run the model classifies correctly.
    ("Then when you draft the email to Devon can you keep it short, use the "
     "same numbers from the last invoice, make sure the due date is the "
     "fifteenth, and please attach the updated scope document before it "
     "goes out so that nothing is missing.",
     {"decision": "act", "goal": "draft and send the Devon invoice email",
      "addressee": "dictation", "reason": "dictating an email"}),
    # Short trailing fragments of the same dictation — too short for the
    # floor; the model (helped by the sticky context) classifies them.
    ("Also make the reload button say reloading while it spins.",
     {"decision": "act", "goal": "update the reload button label",
      "addressee": "dictation", "reason": "dictated instruction"}),
    # A read-only ask inside the dictation: research is allowed, quietly.
    ("Can you double check that the store listing page is actually live.",
     {"decision": "act",
      "goal": "check if the chrome web store listing is live",
      "addressee": "dictation", "reason": "read-only check"}),
    # A long run where the model omits the addressee field entirely.
    ("After that update the readme to explain the pairing flow, change the "
     "screenshots to the new dark theme, and make sure the version number "
     "in the manifest matches the one in the store listing before you "
     "upload the package tonight.",
     {"decision": "act",
      "goal": "update the readme and upload the extension package",
      "reason": "instructions heard"}),
    ("And that should be everything for tonight.",
     {"decision": "ignore", "goal": None, "addressee": "dictation",
      "reason": "no action"}),
]

# Afterwards, he actually speaks to HER — the fix must be a lane, not a mute.
DIRECT_ASK = ("Anticipy, can you book the usual table at Cactus Club for "
              "Friday at seven.",
              {"decision": "act",
               "goal": "book a table at Cactus Club for Friday 7pm",
               "addressee": "assistant", "reason": "direct ask"})

llm = ScriptedLLM([r for _, r in SESSION] + [DIRECT_ASK[1]])
a = Offline(llm)

outs = [a.hear(line) for line, _ in SESSION]

said = [o["anticipy_says"] for o in outs if o["anticipy_says"]]
check("zero texts across the whole dictation session", a.texts == [],
      f"{a.texts}")
check("zero things said across the whole dictation session", said == [],
      f"{said}")
check('zero "On it" anywhere, letter of the definition of done',
      not any("on it" in s.lower() for s in said))
held = [q for q in a.queued if q["hold"]]
check("zero held jobs — nothing waits on an OK he never gave", held == [],
      f"{held}")
check("no dictated line is stamped act or ask — the feed shows no bolt",
      all(o["decision"].decision not in ("act", "ask") for o in outs),
      str([o["decision"].decision for o in outs]))
check("every dictated line is stamped with its addressee",
      all(o["decision"].addressee == "dictation" for o in outs),
      str([o["decision"].addressee for o in outs]))
check("the read-only check still happened, quietly",
      len(a.queued) == 1 and a.queued[0]["hold"] is False
      and a.queued[0]["params"].get("lane") == "ambient",
      f"{a.queued}")
check("the sticky context carried the classification into the short lines",
      "(Addressee of the previous line: dictation)" in llm.triage_prompts[2],
      llm.triage_prompts[2])

# --- and then the one line that WAS for her ---------------------------------
out = a.hear(DIRECT_ASK[0])
check("the direct ask right after the session still acts",
      out["decision"].decision == "act", out["decision"].decision)
check("its booking is held for his OK",
      a.queued[-1]["goal"].startswith("book") and a.queued[-1]["hold"] is True,
      f"{a.queued[-1]}")
check("and he is told about that one, and only that one",
      len(a.texts) == 1, f"{a.texts}")

print(f"\n2026-08-04 replay: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
