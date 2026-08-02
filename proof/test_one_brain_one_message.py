#!/usr/bin/env python3
"""Everything he says reaches her brain, and she answers once.

Two faults found by asking what happens when he texts something NEW while
tasks are blocked, replayed against the live model:

  him: "what's the weather in Vancouver today?"
  her: "I'm not able to look up the weather right now."

She can. That is exactly the kind of thing she does — the browser looks it
up. The SMS classifier had decided it was small talk, so the request never
reached triage at all, and then invented an incapacity to explain itself.
Only "new_request" was ever handed to hear(); "chat" was a dead end where
anything misfiled went to die.

The second fault is quieter. Anything routed to hear() could speak for
itself, so a new request produced TWO texts: the classifier's "got it, I can
look into that" and moments later hear()'s own "want me to go ahead?". Same
thread, same thought, twice.

So: triage is the authority on what is actionable, not the classifier — a
genuinely social line comes back "ignore" and her warm reply stands. And
whatever she decides to say comes back as THIS reply instead of a second
message.

Usage:  PYTHONPATH=. python3 proof/test_one_brain_one_message.py
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


class Resp:
    ok = True
    def __init__(self, items=None, single=None):
        self._items = items or []
        self._single = single
    def json(self):
        return self._single if self._single is not None else {"items": self._items}


def build(intent: str, triage: str, says: str = "Want me to go ahead?"):
    """Returns (convo, heard, texted_separately)."""
    heard, texted = [], []

    def get(url, **kw):
        if "/jobs/records/" in url:
            return Resp(single={})
        return Resp([])
    C.pb.get, C.pb.post, C.pb.patch = get, (lambda *a, **k: Resp()), (lambda *a, **k: Resp())

    class LLM:
        live = True
        def chat(self, system, user, **kw):
            return types.SimpleNamespace(text=json.dumps(
                {"intent": intent, "pending_id": None, "changes": None,
                 "reply": "Got it, I can look into that."}))

    def hear(text, context=None, may_say=None):
        heard.append(text)
        # hear() speaks for itself unless the caller says not to — that is
        # the exact double-text this test exists to prevent.
        if triage in ("act", "ask") and (not may_say or may_say(says, "", triage)):
            texted.append(says)
        return {"decision": types.SimpleNamespace(decision=triage, goal="g"),
                "anticipy_says": says if triage in ("act", "ask") else ""}

    anticipy = types.SimpleNamespace(
        owner_id="X", backend_url="http://pb", llm=LLM(),
        memory=types.SimpleNamespace(recall=lambda *a, **k: []),
        hear=hear, _voice=lambda ctx: None)
    convo = C.Conversation(anticipy=anticipy, llm=LLM(), transport=None)
    convo._pending = lambda: []
    convo._blocked = lambda: []
    convo._remember_about_owner = lambda t: {}
    convo._resume_stuck = lambda learned=None: None
    convo.say = lambda phone, msg: None
    return convo, heard, texted


# --- a question filed as small talk still reaches her brain -----------------
convo, heard, texted = build("chat", "act")
out = convo.on_reply("+1", "what's the weather in Vancouver today?")
check("a request misfiled as small talk still reaches her brain",
      heard == ["what's the weather in Vancouver today?"], f"{heard}")
check("and she answers it instead of claiming she cannot",
      out["reply"] == "Want me to go ahead?", f"{out['reply']!r}")

# --- genuinely social stays social -----------------------------------------
convo, heard, texted = build("chat", "ignore")
out = convo.on_reply("+1", "haha that's funny")
check("small talk is still passed to triage", heard == ["haha that's funny"])
check("but triage calling it nothing leaves her warm reply alone",
      out["reply"] == "Got it, I can look into that.", f"{out['reply']!r}")

# --- one thought, one message ----------------------------------------------
convo, heard, texted = build("new_request", "act")
out = convo.on_reply("+1", "book me a haircut for Thursday")
check("a new request does not produce a second text",
      texted == [], f"hear() also sent: {texted}")
check("her decision comes back as the reply itself",
      out["reply"] == "Want me to go ahead?", f"{out['reply']!r}")

# --- a core without the hook must not lose the thought ----------------------
heard2 = []
def old_hear(text, context=None):          # no may_say parameter at all
    heard2.append(text)
    return {"decision": types.SimpleNamespace(decision="act", goal="g"),
            "anticipy_says": "Older core."}
convo, _, _ = build("new_request", "act")
convo.anticipy.hear = old_hear
out = convo.on_reply("+1", "book me a haircut")
check("an older brain without the hook still gets the thought",
      heard2 == ["book me a haircut"], f"{heard2}")

# --- a brain that throws must not swallow his message silently -------------
def angry_hear(text, context=None, may_say=None):
    raise RuntimeError("triage exploded")
convo, _, _ = build("new_request", "act")
convo.anticipy.hear = angry_hear
out = convo.on_reply("+1", "book me a haircut")
check("if triage explodes she still replies something",
      bool(out.get("reply")), f"{out}")

print(f"\none brain, one message: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
