#!/usr/bin/env python3
"""WHO is he talking to? (roadmap §7.1, brief 02)

On 2026-08-04 the owner spent part of his day dictating messages to another
AI through voice-to-text. Every dictated run reached triage looking exactly
like a request, triage did its job — "err toward starting work" — and he
got "On it" fires about messages that were never aimed at her.

The fix under test, in three layers:
  * triage now also answers WHO the owner is addressing (assistant | person
    | dictation | self), folded into the one existing call — no extra stage;
  * a deterministic pre-filter OUTSIDE the model catches the unmistakable
    case (a very long fluent run of instruction-prose) even when the model
    misclassifies it;
  * dictation- and person-directed speech lands in the ambient lane:
    remembered, researched quietly when the work is read-only, but NEVER a
    text and NEVER a held job waiting on his OK.

And the honesty wall: a missing or invalid addressee field must change
NOTHING — the behaviour she had before this field existed is the fallback,
so a misbehaving model cannot regress her.

Usage:  PYTHONPATH=. python3 proof/test_addressee.py
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime

import brain.anticipy_core as A
import brain.worker as W
from brain.anticipy_core import Anticipy, looks_like_dictation
from brain.orchestrator import ADDRESSEES, AMBIENT_ADDRESSEES

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))


# --------------------------------------------------------------- scaffolding

class ScriptedLLM:
    """Returns the next scripted triage JSON; records what triage was asked
    so the sticky-context contract can be asserted on the prompt itself."""
    live = True

    def __init__(self, *triage_responses: dict):
        self.queue = list(triage_responses)
        self.triage_prompts: list[str] = []

    def chat(self, system, user, **kw):
        if '"decision"' in (system or ""):          # the triage contract
            self.triage_prompts.append(user)
            return types.SimpleNamespace(text=json.dumps(self.queue.pop(0)))
        # her voice, briefings, recall — some plain sentence
        return types.SimpleNamespace(text="Okay — want me to go ahead?")


class Offline(Anticipy):
    """No PocketBase, no Twilio: the queue and the phone are recorders."""

    def __init__(self, llm):
        mem = types.SimpleNamespace(
            ingest=lambda *a, **k: {"commitment_id": None},
            recall=lambda *a, **k: [],
            open_loops=lambda: [],
            close_from_speech=lambda *a, **k: [],
            briefing_facts=lambda *a, **k: {"heard": [], "open_loops": []})
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


def hear(line: str, *triage_responses: dict, explicit: bool = False):
    a = Offline(ScriptedLLM(*triage_responses))
    out = a.hear(line, explicit=explicit)
    return a, out


# A dictated run long and fluent enough for the deterministic pre-filter:
# 40+ words, instruction-prose, no fillers, no interlocutor.
LONG_DICTATION = ("Okay so in the message to the team make sure you mention "
                  "that the extension kept opening tabs on top of me all "
                  "night, and please ask whether we can move the research "
                  "jobs off my browser entirely, and then add a line about "
                  "the store listing review timeline.")


# ------------------------------------------------- the ambient lane: dictation

a, out = hear("Tell them the deploy is done and they can start testing the pairing flow now.",
              {"decision": "act", "goal": "send a message to the team that the deploy is done",
               "addressee": "dictation", "reason": "dictating a message"})
check("a dictated send produces no text", a.texts == [], f"{a.texts}")
check("a dictated send produces no job at all", a.queued == [], f"{a.queued}")
check("and she says nothing", out["anticipy_says"] is None,
      f"{out['anticipy_says']!r}")
check("the feed reads it as left alone", out["decision"].decision == "ignore",
      out["decision"].decision)
check("the addressee is logged for the audit trail",
      out["decision"].addressee == "dictation", str(out["decision"].addressee))
check("the goal she declined to start is preserved on the record",
      out["decision"].goal is not None)

# ---------------------------------- the deterministic floor beats a bad model

a, out = hear(LONG_DICTATION,
              {"decision": "act", "goal": "draft and send a message to the team",
               "addressee": "assistant", "reason": "owner asked me"})
check("the pre-filter itself knows this line", looks_like_dictation(LONG_DICTATION))
check("a model calling long dictation 'assistant' is overridden",
      out["decision"].addressee == "dictation", str(out["decision"].addressee))
check("so even a misclassifying model cannot fire a text",
      a.texts == [] and a.queued == [] and out["anticipy_says"] is None)

# ----------------------------------------------------- direct asks still act

a, out = hear("Can you send Sarah the pitch deck tonight?",
              {"decision": "act", "goal": "send Sarah the pitch deck",
               "addressee": "assistant", "reason": "direct ask"})
check("a direct ask still queues the job", len(a.queued) == 1, f"{a.queued}")
check("consequential work is still held for his OK",
      a.queued and a.queued[0]["hold"] is True)
check("and he is still told about it", len(a.texts) == 1, f"{a.texts}")
check("she still speaks to the feed", bool(out["anticipy_says"]))
check("assistant addressee is logged too",
      out["decision"].addressee == "assistant")

# ------------------------------------- person-to-person: research, no texting

a, out = hear("We should figure out flights to Vienna in October.",
              {"decision": "act", "goal": "research flight options to Vienna for October",
               "addressee": "person", "reason": "planning together"})
check("person-to-person planning may research", len(a.queued) == 1, f"{a.queued}")
check("the research is queued unheld — no confirmation prompt",
      a.queued and a.queued[0]["hold"] is False)
check("the job is marked ambient so its result stays off his phone",
      a.queued and a.queued[0]["params"].get("lane") == "ambient",
      str(a.queued and a.queued[0]["params"]))
check("the quiet work is tracked as a loop",
      len(a.loops) == 1 and a.loops[0].status == "handling")
check("but nothing is texted", a.texts == [], f"{a.texts}")
check("and nothing is said", out["anticipy_says"] is None)

a, out = hear("Let's book the Vienna flights tomorrow.",
              {"decision": "act", "goal": "book flights to Vienna",
               "addressee": "person", "reason": "they agreed"})
# This case used to assert the opposite — that the job "is not even queued".
# That assertion is what killed the product on 2026-08-04: Omar agreed a
# whole dinner out loud with a friend (Cactus Club, park location, 7pm, two
# people) and every line of it came back "Noted — nothing needed", because
# a plan made WITH SOMEONE ELSE could never become work. That is the single
# strongest signal Anticipy gets — another human is holding him to it — so
# binning it removed the reason the product exists.
#
# The lane was answering the wrong question. "May she SPEAK about this?" and
# "May she WORK on this?" are separate; wave 1 collapsed them, turning
# "interrupt almost never" into "do nothing". Silence is still absolute here
# — what changes is that the work gets prepared and waits on his desk.
check("a plan agreed with another person becomes real, prepared work",
      len(a.queued) == 1, f"{a.queued}")
check("and it is HELD — she prepares it, she does not book it behind his back",
      a.queued and a.queued[0]["hold"] is True, f"{a.queued}")
check("the card goes to her desk, not down the ambient hole",
      a.queued and a.queued[0]["params"].get("lane") == "desk",
      str(a.queued and a.queued[0]["params"]))
# 2026-08-05: silence here was overturned by Omar himself — the held dinner
# card sat unseen while he waited for a text that never came. Held work now
# earns exactly ONE text asking for his go-ahead (and any missing details).
check("and he is texted ONCE for his go-ahead — held work never sits silent",
      len(a.texts) == 1 and out["anticipy_says"], f"{a.texts}")

a, out = hear("Maybe the trip should be that first week.",
              {"decision": "ask", "goal": "plan the Vienna trip",
               "missing": ["which dates"], "addressee": "person",
               "reason": "needs dates"})
# 2026-08-05, second revision: "plan X" is read-only preparation now, and
# read-only prep ALWAYS starts quietly — dates unknown means research both
# weeks, not stand idle and not interrupt his conversation. The results
# reach him as the FYI text when they land.
check("read-only prep with an unknown still starts, quietly, unheld",
      len(a.queued) == 1 and a.queued[0]["hold"] is False
      and a.queued[0]["params"].get("lane") == "ambient",
      f"{a.queued}")
check("and nothing is said or texted about starting it",
      a.texts == [] and out["anticipy_says"] is None, f"{a.texts}")

a, out = hear("We should book that boat tour when we know the day.",
              {"decision": "ask", "goal": "book the Vienna boat tour",
               "missing": ["which day"], "addressee": "person",
               "reason": "needs the day"})
check("a CONSEQUENTIAL plan with unknowns is held and asked about once",
      a.queued and a.queued[0]["hold"] is True and len(a.texts) == 1
      and "which day" in str(a.queued[0]["params"].get("missing")),
      f"{a.queued} {a.texts}")

# ------------------------------------------- self-talk keeps today's behaviour

a, out = hear("I really should cancel that gym membership.",
              {"decision": "act", "goal": "cancel the gym membership",
               "addressee": "self", "reason": "mumbled commitment"})
check("thinking aloud still gets her help — that is the product",
      len(a.queued) == 1 and len(a.texts) == 1, f"{a.queued} {a.texts}")

# --------------------------------------------------- fail open, twice over

a, out = hear("I'll send Marcus the invoice tonight.",
              {"decision": "act", "goal": "send Marcus the invoice",
               "reason": "commitment"})
check("no addressee field at all changes nothing",
      len(a.queued) == 1 and len(a.texts) == 1 and a.queued[0]["hold"] is True,
      f"{a.queued} {a.texts}")
check("the unclassified line is logged as unclassified",
      out["decision"].addressee is None)

a, out = hear("I'll send Marcus the invoice tonight.",
              {"decision": "act", "goal": "send Marcus the invoice",
               "addressee": "the-room", "reason": "commitment"})
check("an invalid addressee value changes nothing either",
      len(a.queued) == 1 and len(a.texts) == 1,
      f"{a.queued} {a.texts}")

# ------------------------------------------------- sticky within a conversation

llm = ScriptedLLM(
    {"decision": "ignore", "goal": None, "addressee": "dictation",
     "reason": "dictating"},
    {"decision": "ignore", "goal": None, "addressee": "dictation",
     "reason": "still dictating"})
a = Offline(llm)
a.hear("Also change the error message to say the pairing code expired.")
a.hear("And keep the retry button where it is.")
check("the previous classification rides along as context",
      "(Addressee of the previous line: dictation)" in llm.triage_prompts[1],
      llm.triage_prompts[1])
check("the first line of a conversation carries no such context",
      "Addressee of the previous line" not in llm.triage_prompts[0])

llm = ScriptedLLM(
    {"decision": "act", "goal": "draft the team message",
     "addressee": "assistant", "reason": "misclassified"},
    {"decision": "ignore", "goal": None, "addressee": "dictation",
     "reason": "dictating"})
a = Offline(llm)
a.hear(LONG_DICTATION)
a.hear("And keep the retry button where it is.")
check("the pre-filter's verdict feeds the stickiness, not the model's",
      "(Addressee of the previous line: dictation)" in llm.triage_prompts[1],
      llm.triage_prompts[1])
check("the pre-filter announces itself to the model",
      "(Pre-check:" in llm.triage_prompts[0], llm.triage_prompts[0])

# --------------------------------------- explicit lines are his own words

a, out = hear("look up the weather in Montreal",
              {"decision": "act", "goal": "look up the weather in Montreal",
               "addressee": "dictation", "reason": "model is confused"},
              explicit=True)
check("a line he typed AT her is assistant by definition",
      out["decision"].addressee == "assistant", str(out["decision"].addressee))
check("and it runs", len(a.queued) == 1, f"{a.queued}")

# --------------------------------------------- a dictated question stays quiet

llm = ScriptedLLM({"decision": "ignore", "goal": None,
                   "addressee": "dictation", "reason": "dictation"})
a = Offline(llm)
q = ("What do you think is the cleanest way to make sure the pairing screen "
     "autofills the code from the clipboard, and could you please also "
     "update the store listing copy so that it mentions the new tab sweeping "
     "behaviour, and then add a screenshot of the dark theme somewhere?")
out = a.hear(q)
check("a long dictated question is not answered from memory as if he asked HER",
      out["decision"].decision != "answer", out["decision"].decision)

# --------------------------------------------------- the pre-filter, unit-level

check("short lines never trip the pre-filter",
      not looks_like_dictation("Can you book the usual table for Friday?"))
check("long but disfluent speech is a person, not a machine",
      not looks_like_dictation(
          "So um I was thinking, you know, that we could maybe take the "
          "ferry across and then, I mean, drive up the coast and make sure "
          "we stop at that bakery you like and please remind me to bring "
          "the good camera because last time the light was unbelievable "
          "and we missed it completely."))
check("naming her makes it a line for her, however long",
      not looks_like_dictation(LONG_DICTATION.replace(
          "the message to the team", f"the message to {A.NAME}")))
check("chatter without instruction-prose stays unfiltered",
      not looks_like_dictation(
          "The drive down was longer than we thought and the weather kept "
          "changing the whole way but the coast was beautiful and we found "
          "a little place for lunch right on the water and stayed there "
          "most of the afternoon watching the boats come in and out of "
          "the harbour until it got dark."))
check("empty input is not dictation", not looks_like_dictation(""))

# ============================================================= worker plumbing

assert W.pb is A.pb, "if these ever diverge, patch both"


class Resp:
    def __init__(self, items=None, single=None):
        self.ok = True
        self._items = items or []
        self._single = single
    def json(self):
        return self._single if self._single is not None else {"items": self._items}
    def raise_for_status(self):
        pass


PATCHES: list[tuple[str, dict]] = []
POSTS: list[tuple[str, dict]] = []
JOBS: list[dict] = []


def fake_get(url, **kw):
    if "/jobs/records" in url:
        return Resp(items=list(JOBS))
    return Resp(items=[])            # events: nothing said yet


def fake_post(url, **kw):
    POSTS.append((url, kw.get("json")))
    return Resp(single={"id": "e1"})


def fake_patch(url, **kw):
    PATCHES.append((url, kw.get("json")))
    return Resp()


W.pb.get, W.pb.post, W.pb.patch = fake_get, fake_post, fake_patch

# --- the decision AND the addressee land on the event record
W.mark_processed("ev1", "ignore", addressee="dictation")
check("the worker stamps the addressee beside the decision",
      PATCHES[-1][1] == {"decision": "ignore", "addressee": "dictation"},
      str(PATCHES[-1]))
W.mark_processed("ev2", "act")
check("no classification stamps no addressee",
      PATCHES[-1][1] == {"decision": "act"}, str(PATCHES[-1]))

# --- ambient jobs are recognised whichever shape params arrives in
check("ambient_job reads the lane from encoded params",
      W.ambient_job({"params": json.dumps({"lane": "ambient"})}))
check("ambient_job reads the lane from decoded params",
      W.ambient_job({"params": {"lane": "ambient"}}))
check("a job without the lane is not ambient",
      not W.ambient_job({"params": json.dumps({"source": "x"})}))
check("garbage params are not ambient", not W.ambient_job({"params": "{{{"}))

# --- a finished ambient job lands in the feed, never on his phone
TEXTS: list[str] = []
fake_anticipy = types.SimpleNamespace(
    owner_id="",
    _voice=lambda ctx: None,
    notify_owner=lambda m, channel="sms": (TEXTS.append(m), {"sent": True})[1])

W.REPORTED.clear()
JOBS[:] = [{"id": "amb1", "goal": "research flight options to Vienna",
            "params": json.dumps({"lane": "ambient"}),
            "result": "Two direct options under $900 in October.",
            "status": "done"}]
POSTS.clear()
W.report_finished_jobs(fake_anticipy)
# Rule change 2026-08-05 (Omar): quiet work is no longer invisible work.
# A finished overheard lookup sends ONE light FYI text — he watched her
# research Paris flights, saw only "Noted — nothing needed", and reasonably
# concluded she was dead. (This rig runs at a daytime hour only if the wall
# clock says so; the quiet-hours branch is unit-tested in tests/.)
from datetime import datetime as _dt
_quiet_now = (W.CLOCK_QUIET_START <= _dt.now(W.CLOCK_TZ).hour
              or _dt.now(W.CLOCK_TZ).hour < W.CLOCK_QUIET_END)
if _quiet_now:
    check("an overheard result holds its text through quiet hours",
          TEXTS == [], f"{TEXTS}")
else:
    check("a finished overheard lookup texts ONE fyi",
          len(TEXTS) == 1 and "October" in TEXTS[0], f"{TEXTS}")
check("and it lands in the feed",
      any((p[1] or {}).get("kind") == "anticipy_says" and
          "October" in (p[1] or {}).get("text", "") for p in POSTS),
      str(POSTS))
check("and the job is not reported twice", "amb1" in W.REPORTED)

# --- a finished NORMAL job still reaches him (no regression)
W.REPORTED.clear()
JOBS[:] = [{"id": "norm1", "goal": "check the ferry schedule",
            "params": json.dumps({"source": "he asked"}),
            "result": "Last ferry is 9pm.", "status": "done"}]
TEXTS.clear()
W.report_finished_jobs(fake_anticipy)
check("a job he asked for still gets its answer texted",
      len(TEXTS) == 1, f"{TEXTS}")

# --- a stuck ambient job earns no text either
JOBS[:] = [{"id": "amb2", "goal": "research hotels",
            "params": json.dumps({"lane": "ambient"}),
            "result": "I need a login to see prices.", "status": "needs_user"}]
TEXTS.clear()
W.ask_about_stuck_jobs(fake_anticipy, None)
check("a blocked ambient job stays quiet", TEXTS == [], f"{TEXTS}")

JOBS[:] = [{"id": "norm2", "goal": "book the table",
            "params": json.dumps({"source": "he asked"}),
            "result": "I need his first name.", "status": "needs_user"}]
TEXTS.clear()
W.ask_about_stuck_jobs(fake_anticipy, None)
check("a blocked job he asked for still reaches him", len(TEXTS) == 1, f"{TEXTS}")

# --- a stalled ambient job does not buzz him about a browser he never engaged

class FrozenDT(datetime):
    """Freeze ONLY the clock reading report_stalled_work consults, at a
    civilised local hour so quiet-hours logic stays out of the way."""
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 4, 14, 0, tzinfo=tz)


_real_dt = W.datetime
W.datetime = FrozenDT
try:
    JOBS[:] = [{"id": "amb3", "goal": "research the ferry",
                "params": json.dumps({"lane": "ambient"}),
                "status": "queued", "updated": "2026-08-04 10:00:00"}]
    TEXTS.clear()
    W.report_stalled_work(fake_anticipy)
    check("a stalled ambient job stays quiet", TEXTS == [], f"{TEXTS}")

    JOBS[:] = [{"id": "norm3", "goal": "book the table",
                "params": json.dumps({"source": "he asked"}),
                "status": "queued", "updated": "2026-08-04 10:00:00"}]
    TEXTS.clear()
    W.report_stalled_work(fake_anticipy)
    check("a stalled job he asked for is still raised", len(TEXTS) == 1,
          f"{TEXTS}")
finally:
    W.datetime = _real_dt

print(f"\naddressee classification: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
