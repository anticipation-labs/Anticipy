#!/usr/bin/env python3
"""What would ACTUALLY happen if he replied right now — against real records.

Every other proof in this directory runs the real code against fakes I wrote.
That catches logic errors and misses shape errors: a field that is named
something else in production, a requirement string that does not match the way
I assumed, a job whose params are not the shape the matcher expects. This runs
the real conversation code against the REAL production backend, with every
write intercepted, and reports what would have happened.

Nothing is created, patched or sent. Reads are live; writes are captured and
printed. Run it through the worker's environment so the model is the same one
production uses:

    cd ~/Anticipy-pendant
    railway run --service worker python3 proof/dry_run_his_reply.py

    railway run --service worker python3 proof/dry_run_his_reply.py "no, I never said that about car insurance"
"""
from __future__ import annotations

import json
import sys
import types

import brain.conversation as C
from brain.llm import LLM

REPLY = sys.argv[1] if len(sys.argv) > 1 else \
    "Omar Ebrahim, omarkebrahim@gmail.com, 604 724 5161"

WRITES: list[tuple[str, str, dict]] = []
SENT: list[str] = []

_real_patch, _real_post = C.pb.patch, C.pb.post


def blocked_patch(url, **kw):
    WRITES.append(("PATCH", url.split("/api/")[-1], kw.get("json") or {}))
    class R:
        ok = True
        def json(self): return {}
    return R()


def blocked_post(url, **kw):
    WRITES.append(("POST", url.split("/api/")[-1], kw.get("json") or {}))
    class R:
        ok = True
        def json(self): return {"id": "would-have-created"}
        def raise_for_status(self): pass
    return R()


C.pb.patch, C.pb.post = blocked_patch, blocked_post

llm = LLM()
if not llm.live:
    sys.exit("no live LLM in env — run via: railway run --service worker")

OWNER = "D2846190-381B-4AF8-8F15-3E5B986B5D5F"
BASE = "https://backend-production-61e0a.up.railway.app"

heard = []
anticipy = types.SimpleNamespace(
    owner_id=OWNER, backend_url=BASE, llm=llm,
    memory=types.SimpleNamespace(recall=lambda *a, **k: []),
    hear=lambda text, context=None, may_say=None: heard.append(text) or {},
    # The REAL voice, not a stub returning None. A stub here sends every
    # caller down its fallback path, which is not what production does — and
    # that difference hid how bad one fallback actually was.
    _voice=lambda ctx: (llm.chat(
        "You are Anticipy texting your owner. One or two sentences, warm, "
        "plain, no emojis. Return only the message.",
        json.dumps(ctx), temperature=0.7).text.strip().strip('"') or None),
)

convo = C.Conversation(anticipy=anticipy, llm=llm, transport=None)
convo.say = lambda phone, msg: SENT.append(msg)

print(f"HIS REPLY: {REPLY!r}\n")

print("what she can see right now, read live:")
for b in convo._blocked():
    print(f"  · {b['goal'][:52]}")
    print(f"      needs now : {(b['needs'] or '(nothing)')[:88]}")
    print(f"      remembered: {(b.get('remembered_need') or '(none)')[:88]}")
print()

out = convo.on_reply("+16047245161", REPLY)

print(f"understood as : {out.get('intent')!r}")
print(f"she would say : {(out.get('reply') or '')[:150]}")
print()
print("writes she would have made (NONE were actually sent):")
if not WRITES:
    print("  · none")
for verb, path, body in WRITES:
    keys = {k: (str(v)[:70] + "…" if len(str(v)) > 70 else v)
            for k, v in body.items()}
    print(f"  · {verb} {path}")
    for k, v in keys.items():
        print(f"       {k}: {v}")
print()

flips = [(p, b) for verb, p, b in WRITES if verb == "PATCH" and "jobs" in p]
resumed = [p for p, b in flips if b.get("status") == "queued"]
cancelled = [p for p, b in flips if b.get("status") == "cancelled"]
facts = [b for verb, p, b in WRITES if "owner_profile" in p]

print("VERDICT")
print(f"  facts she would store  : "
      f"{list(json.loads(facts[0].get('facts', '{}')).keys()) if facts else 'none'}")
print(f"  tasks she would resume : {[p.split('/')[-1] for p in resumed] or 'none'}")
print(f"  tasks she would cancel : {[p.split('/')[-1] for p in cancelled] or 'none'}")
print(f"  passed to her brain    : {heard or 'nothing'}")
print()
print("Read-only: no records were changed and no text was sent.")
