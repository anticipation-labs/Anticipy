"""'Both' / 'all' / 'neither' must answer her numbered question.

On 2026-08-03 she asked "which one should I call off: 1) ... 2) ...?", he
replied "Both", and she asked the identical question three times. These tests
pin the fix: a whole-list answer acts on every offered job, 'neither' to a
cancel offer keeps them, and the identical text is never sent twice in a row.

Run: PYTHONPATH=. python3 proof/test_group_choice.py
"""
from __future__ import annotations

import sys

from brain.conversation import Conversation, MockTransport


class FakeMemory:
    def recall(self, text, limit=3):
        return []


class FakeAnticipy:
    llm = None
    owner_id = ""
    owner_phone = "+15550001111"
    backend_url = "http://127.0.0.1:1"   # never reached — everything is stubbed
    memory = FakeMemory()


def make(jobs):
    convo = Conversation(FakeAnticipy(), transport=MockTransport())
    state = {j["id"]: j for j in jobs}

    convo._pending = lambda: [j for j in state.values()
                              if j["status"] == "awaiting_confirm"]
    convo._blocked = lambda: [j for j in state.values()
                              if j["status"] == "needs_user"]
    convo._open_work = lambda: convo._pending() + convo._blocked()
    convo._fetch = lambda jid: state.get(jid)
    convo._remember_about_owner = lambda text: {}
    # b883258 gave _think the phone so it can carry the SMS thread; this rig
    # only needs it to stay out of the way.
    convo._think = lambda text, phone=None: None

    def flip(jid, fields, verb):
        state[jid].update(fields)
        return f"{verb}:{jid}"
    convo._flip = flip
    return convo, state


JOBS = [
    {"id": "j1", "goal": "car_insurance_renewal", "status": "awaiting_confirm", "params": "{}"},
    {"id": "j2", "goal": "confirm_dinner_plans", "status": "awaiting_confirm", "params": "{}"},
]

passed = 0


def check(name, cond):
    global passed
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        sys.exit(1)
    passed += 1


# 1. "Both" after a cancel offer cancels both — and does not re-ask.
convo, state = make([dict(j) for j in JOBS])
convo._which_one(cancel=True)
out = convo.on_reply("+15550001111", "Both")
check("'Both' after a cancel offer cancels both jobs",
      state["j1"]["status"] == "cancelled" and state["j2"]["status"] == "cancelled")
check("...and the reply is not the question again",
      "which one" not in out["reply"].lower())

# 2. "both" after a go-ahead offer releases both.
convo, state = make([dict(j) for j in JOBS])
convo._which_one(cancel=False)
out = convo.on_reply("+15550001111", "yes both")
check("'yes both' after a go-ahead offer releases both",
      state["j1"]["status"] == "queued" and state["j2"]["status"] == "queued")

# 3. "neither" after a cancel offer keeps them all.
convo, state = make([dict(j) for j in JOBS])
convo._which_one(cancel=True)
out = convo.on_reply("+15550001111", "neither")
check("'neither' after a cancel offer keeps both",
      state["j1"]["status"] == "awaiting_confirm"
      and state["j2"]["status"] == "awaiting_confirm")

# 4. "neither" after a go-ahead offer cancels both — don't do either.
convo, state = make([dict(j) for j in JOBS])
convo._which_one(cancel=False)
out = convo.on_reply("+15550001111", "neither")
check("'neither' after a go-ahead offer cancels both",
      state["j1"]["status"] == "cancelled" and state["j2"]["status"] == "cancelled")

# 5. An ordinary sentence containing no group word changes nothing.
convo, state = make([dict(j) for j in JOBS])
convo._which_one(cancel=True)
convo.on_reply("+15550001111", "let me think about it")
check("a non-answer leaves both jobs untouched",
      state["j1"]["status"] == "awaiting_confirm"
      and state["j2"]["status"] == "awaiting_confirm")

# 6. The identical text is never sent twice in a row within minutes.
convo, state = make([dict(j) for j in JOBS])
convo.say("+15550001111", "Just to be sure — which one?")
convo.say("+15550001111", "Just to be sure — which one?")
sent = [m for m in convo.transport.sent]
check("an identical repeat within minutes is not sent", len(sent) == 1)
convo.say("+15550001111", "something different")
check("...but a different text still goes out", len(convo.transport.sent) == 2)

# 7. LLM-first: the model names several items itself ("nah scrap both of
# those") — no keywords involved, its pick is acted on directly.
convo, state = make([dict(j) for j in JOBS])
convo._classify = lambda phone, text: {
    "intent": "decline", "pending_id": None, "pending_ids": ["j1", "j2"],
    "changes": None, "reply": "done — killed them both."}
out = convo.on_reply("+15550001111", "nah scrap those, screw it")
check("model-named multi-decline cancels both, no keywords",
      state["j1"]["status"] == "cancelled" and state["j2"]["status"] == "cancelled")
check("...and her own drafted reply is kept", out["reply"] == "done — killed them both.")

# 8. Answering her question: the model's single pick is trusted without the
# shared-word guard when her last text was a question.
convo, state = make([dict(j) for j in JOBS])
convo.say("+15550001111", "should I lock in the 7:30 or drop it?")
convo._classify = lambda phone, text: {
    "intent": "confirm", "pending_id": "j2", "pending_ids": ["j2"],
    "changes": None, "reply": "locking it in."}
out = convo.on_reply("+15550001111", "yeah do that")
check("model's pick after her question releases without re-asking",
      state["j2"]["status"] == "queued" and "which one" not in out["reply"].lower())

# 9. Explicit texted requests: read-only things run without a confirm gate;
# consequential things are still held.
from brain.anticipy_core import is_consequential  # noqa: E402

check("'Open Wikipedia in browser' (explicit) runs without a hold",
      not is_consequential("Open Wikipedia in browser", explicit=True))
check("'Open Wikipedia in browser' (overheard) also read-only now",
      not is_consequential("Open Wikipedia in browser"))
check("'book Cactus Club for 7:30' still held even when explicit",
      is_consequential("book Cactus Club for 7:30", explicit=True))
check("'send the email to Marcus' still held even when explicit",
      is_consequential("send the email to Marcus", explicit=True))
check("explicit non-read-only, non-consequential runs ('organize my tabs')",
      not is_consequential("organize my tabs", explicit=True))
check("overheard non-read-only still held by default",
      is_consequential("organize my tabs"))

# 10. "Do it" seconds after asking: the freshest pending item is released
# instead of a numbered menu.
convo, state = make([dict(j) for j in JOBS])
now_iso = __import__("datetime").datetime.now(
    __import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
state["j1"]["created"] = "2026-07-20 01:00:00"          # old
state["j2"]["created"] = now_iso                        # just asked for
convo._classify = lambda phone, text: {
    "intent": "confirm", "pending_id": None, "pending_ids": [],
    "changes": None, "reply": None}
out = convo.on_reply("+15550001111", "Do it")
check("'Do it' releases the just-created item, no menu",
      state["j2"]["status"] == "queued"
      and state["j1"]["status"] == "awaiting_confirm"
      and "which one" not in (out["reply"] or "").lower())

print(f"\n{passed}/{passed} passing")
