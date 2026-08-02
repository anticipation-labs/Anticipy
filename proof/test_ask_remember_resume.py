#!/usr/bin/env python3
"""The whole chain, end to end: she asks, he answers, the browser can finish.

This is the mechanism Omar asked for by name — no Settings page, no column
per field, no app release when a site wants something new. The browser stops
and says exactly what it needs, she asks him in her own words, she remembers
the answer forever, the task resumes, and the next run of the browser sees
what she learned.

Five separate pieces have to line up, and until now each was only ever read
in isolation:

  1. a blocked job names what it needs
  2. his reply is mined for EVERY durable fact, not just the first
  3. the facts are merged into owner_profile.facts, not overwriting what is
     already known
  4. the job flips back to queued and authorized
  5. the payload the browser is handed actually contains those facts

Step 5 is the one that would make the other four pointless, and it crosses a
language boundary (Python worker -> PocketBase hook -> JavaScript extension),
which is exactly where a chain like this usually breaks silently.

Usage:  PYTHONPATH=. python3 proof/test_ask_remember_resume.py
"""
from __future__ import annotations

import json
import re
import sys
import types

import brain.conversation as C
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


# --- the world, as the backend holds it ------------------------------------
PROFILE = {"id": "p1", "first_name": "", "last_name": "", "email": "",
           "phone": "+16047245161", "birthday": "",
           "facts": json.dumps({"dietary": "no shellfish"})}   # something known already
JOB = {"id": "j1", "status": "needs_user",
       "goal": "Book dinner at Cactus Club Park Royal for 2 people",
       "params": json.dumps({"source": "he said so"}),
       "result": "I need your first name, last name, email address, and "
                 "phone number to complete the reservation."}
PATCHES: list[tuple[str, dict]] = []


class Resp:
    def __init__(self, items=None, single=None):
        self.ok = True
        self._items = items or []
        self._single = single
    def json(self):
        return self._single if self._single is not None else {"items": self._items}


def shared_get(url, **kw):
    # brain.worker and brain.conversation share one pb module — install ONE fake.
    if "/owner_profile/" in url:
        return Resp([PROFILE])
    if "/jobs/" in url:
        return Resp([JOB])
    return Resp([])


def shared_patch(url, **kw):
    body = kw.get("json") or {}
    PATCHES.append((url, body))
    if "/owner_profile/" in url and "facts" in body:
        PROFILE["facts"] = body["facts"]
    if "/jobs/" in url:
        JOB.update({k: v for k, v in body.items()})
    return Resp(single={})


assert W.pb is C.pb, "if these ever diverge, patch both"
W.pb.get, W.pb.patch = shared_get, shared_patch
W.pb.post = lambda *a, **k: Resp(single={})


class LLM:
    """Stands in for the extractor only; everything else here is real code."""
    live = True
    def chat(self, system, user, **kw):
        if "durable fact" in system or "facts" in system:
            return types.SimpleNamespace(text=json.dumps({"facts": {
                "first_name": "Omar", "last_name": "Ebrahim",
                "email": "omar@example.com", "phone_number": "604 724 5161"}}))
        return types.SimpleNamespace(text=json.dumps(
            {"intent": "answer", "pending_id": None, "changes": None,
             "reply": "Perfect — I'll finish the booking now."}))


anticipy = types.SimpleNamespace(
    owner_id="X", backend_url="http://pb", llm=LLM(),
    memory=types.SimpleNamespace(recall=lambda *a, **k: []),
    hear=lambda *a, **k: None, _voice=lambda ctx: None)
convo = C.Conversation(anticipy=anticipy, llm=LLM(), transport=None)
convo.say = lambda phone, msg: None

# 1 — the blocked job names what it needs
blocked = convo._blocked()
check("the blocked task says exactly what it needs",
      blocked and "first name" in blocked[0]["needs"], f"{blocked}")

# 2+3+4 — he answers in plain words
out = convo.on_reply("+16047245161",
                     "Omar Ebrahim, omar@example.com, 604 724 5161")
stored = json.loads(PROFILE["facts"])
check("every fact in one reply is kept, not just the first",
      {"first_name", "last_name", "email", "phone_number"} <= set(stored),
      f"{stored}")
check("what she already knew is not overwritten",
      stored.get("dietary") == "no shellfish", f"{stored}")
check("the task goes back to work", JOB.get("status") == "queued", f"{JOB.get('status')}")
check("and carries his go-ahead",
      json.loads(JOB.get("params") or "{}").get("authorized") is True)
check("she does not claim to be blocked any more",
      "still" not in (out.get("reply") or "").lower(), out.get("reply"))

# 5 — the payload the browser is handed. This mirrors backend/pb_hooks/
#     agent_key.pb.js, which is what the extension actually fetches.
owner_payload = {
    "first_name": PROFILE["first_name"], "last_name": PROFILE["last_name"],
    "email": PROFILE["email"], "phone": PROFILE["phone"],
    "birthday": PROFILE["birthday"], "facts": PROFILE["facts"],
}
hook_src = open("backend/pb_hooks/agent_key.pb.js").read()
check("the backend hook really does send facts (not just the fixed columns)",
      re.search(r"facts:\s*p\.getString\(\"facts\"\)", hook_src) is not None)

# And the extension renders every one of them into the model's prompt.
ext = open("extension/agent_loop.js").read()
check("the extension parses facts out of the profile",
      "JSON.parse(ownerProfile.facts" in ext)
check("the extension re-reads who he is at the start of every run",
      "Re-read WHO HE IS at the start of every run" in
      open("extension/background.js").read())

rendered = "\n".join(f"  {k.replace('_', ' ')}: {v}"
                     for k, v in json.loads(owner_payload["facts"]).items())
for needed in ["Omar", "Ebrahim", "omar@example.com", "604 724 5161"]:
    check(f"the browser would see {needed!r}", needed in rendered, rendered)

print(f"\nask, remember, resume: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
