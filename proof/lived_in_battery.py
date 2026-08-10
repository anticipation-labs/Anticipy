"""A lived-in life, end to end over text: preloaded memory, real model.

Not a clean slate. Three days of overheard life are ingested and consolidated
into her profile FIRST — the same polluted, lived-in state the owner's real
account is in — and then realistic conversations and SMS threads run through
the one brain. Every check is a behavior the owner actually hit live.

Run:  PYTHONPATH=. python3 proof/lived_in_battery.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.llm import LLM                      # noqa: E402
from brain.memory import Memory                # noqa: E402
from brain.anticipy_core import Anticipy       # noqa: E402
from brain.conversation import Conversation, MockTransport  # noqa: E402
import brain.anticipy_core as core             # noqa: E402
import brain.conversation as convmod           # noqa: E402

DAYS = [
    ["Morning babe, I'll grab coffee on the way back",
     "Sarah wants to do the farmers market on Sunday again",
     "Yeah I'm still heads down building Anticipy, the assistant startup",
     "I'll send Priya the pitch deck by Thursday",
     "ugh I can never do early mornings, book me afternoon things"],
    ["Gym at six with Marcus again, legs day",
     "Mom's hip surgery got scheduled for the twenty second, I need to be there",
     "Honestly Cactus Club at seven is kind of our default dinner now",
     "I switched to oat milk, dairy has been wrecking me lately"],
    ["where did I put the charger",
     "two zucchinis and a thing of hummus",
     "Sarah and I are thinking Tofino for her birthday in October",
     "Anticipy demo went well, investor wants a follow-up",
     "yeah 7 PM at Cactus Club works, as always"],
]

PHONE = "+15550001111"
CHECKS = []


def check(name, ok, note=""):
    CHECKS.append((name, bool(ok), note))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f" — {note}" if note else ""))


class FakeJobs:
    """In-memory stand-in for the PocketBase jobs table."""
    def __init__(self):
        self.jobs = []

    def post(self, url, json=None, timeout=10):
        rec = {"id": f"j{len(self.jobs)}", "goal": json["goal"],
               "params": json["params"], "status": json["status"],
               "created": "now"}
        self.jobs.append(rec)
        body = dict(rec)

        class R:
            ok = True
            def raise_for_status(self): pass
            def json(self): return body
        return R()

    def patch(self, url, json=None, timeout=10):
        jid = url.rsplit("/", 1)[1]
        for j in self.jobs:
            if j["id"] == jid:
                j.update(json or {})

        class R:
            ok = True
            def json(self): return {}
        return R()

    def get(self, url, params=None, timeout=10):
        if "/records/" in url and not (params or {}).get("filter"):
            jid = url.rsplit("/", 1)[1]
            body = next((j for j in self.jobs if j["id"] == jid), {})
        else:
            body = {"items": [j for j in self.jobs
                              if j["status"] in ("awaiting_confirm", "queued",
                                                 "running", "needs_user")]}

        class R:
            ok = True
            def json(self): return body
        return R()


def build():
    llm = LLM()
    assert llm.live, "needs the live model"
    mem = Memory(":memory:", llm=llm)
    for day in DAYS:
        for line in day:
            mem.ingest(line)
    try:
        mem.consolidate()
    except Exception as e:
        print(f"  (consolidation skipped: {e})")
    fake = FakeJobs()
    core.pb = fake
    convmod.pb = fake
    a = Anticipy(memory=mem, llm=llm, owner_id="lived", owner_phone=PHONE)
    a._pending_jobs = lambda: [j for j in fake.jobs
                               if j["status"] in ("awaiting_confirm",
                                                  "queued")]
    sent = []
    conv = Conversation(a, transport=MockTransport(), llm=llm)
    a.conversation = conv

    def notify(m, channel="sms"):
        # Production texts land in the SMS thread; the classifier reads that
        # thread, so the harness must not bypass it.
        sent.append(m)
        conv.say(PHONE, m)
        return True
    a.notify_owner = notify
    return a, conv, fake, sent


def main():
    a, conv, fake, sent = build()
    say_yes = lambda *x, **k: True

    # ---- 1. a shared plan where the friend owes one detail -------------
    a.hear("Yo good to see you man, we should grab dinner this week. "
           "How about Earls in West Vancouver tomorrow evening? "
           "For sure, let's do that. I'll text you a time.",
           may_say=say_yes)
    cards = [j for j in fake.jobs if j["status"] == "awaiting_confirm"]
    check("shared plan makes exactly one held card", len(cards) == 1,
          f"{[j['goal'] for j in fake.jobs]}")
    check("she texts about it", len(sent) >= 1, f"{sent[:1]}")
    text = " ".join(sent).lower()
    check("no invented time in her text",
          not re.search(r"\b[4-9]\s*(?:pm|p\.m)", text), text[:120])
    claims = re.search(r"\b(booked|got (you )?a (table|reservation))\b", text)
    honest = re.search(r"(nothing'?s? booked|not booked|haven'?t booked|"
                       r"once you|before i book|i'?ll book)", text)
    check("never claims it is booked", not claims or bool(honest), text[:120])
    if cards:
        check("the card keeps the plan's substance",
              "earls" in cards[0]["goal"].lower()
              and "vancouver" in cards[0]["goal"].lower().replace("west van",
                                                                  "vancouver"),
              cards[0]["goal"])

    # ---- 2. SMS answer + go-ahead releases the card ---------------------
    out = conv.on_reply(PHONE, "let's do 7 actually, go ahead")
    released = [j for j in fake.jobs if j["status"] == "queued"]
    check("'let's do 7, go ahead' releases the job",
          out["intent"] == "confirm" and len(released) == 1,
          f"intent={out['intent']} statuses={[j['status'] for j in fake.jobs]}")
    if released:
        p = json.loads(released[0]["params"])
        check("release carries authorization", p.get("authorized") is True)
        blob = (released[0]["goal"] + " " + released[0]["params"]).lower()
        check("the 7 o'clock detail reaches the job", "7" in blob,
              blob[:160])

    # ---- 3. she answers questions from what she knows -------------------
    out = conv.on_reply(PHONE, "what's our usual dinner spot again?")
    ok_spot = "cactus" in (out["reply"] or "").lower()
    if not ok_spot:
        print("    profile:", [f["fact"] for f in a.memory.profile_facts()][:8])
        print("    recall:", [f["fact"] for f in
                              a.memory.recall("what's our usual dinner spot again?",
                                              limit=6)])
    check("knows the usual spot from memory", ok_spot, out["reply"])
    out = conv.on_reply(PHONE, "when is my mom's surgery?")
    check("knows mom's surgery date",
          re.search(r"(22|twenty[- ]second)", (out["reply"] or "").lower())
          is not None, out["reply"])

    # ---- 4. someone else's errand stays theirs --------------------------
    n_jobs = len(fake.jobs)
    r = a.hear("Don't worry about the flights, leave them with me, "
               "I'll sort them out and send you the confirmation.",
               may_say=say_yes)
    check("a friend's errand makes no card", len(fake.jobs) == n_jobs,
          f"{[j['goal'] for j in fake.jobs[n_jobs:]]}")
    check("and carries no goal to the feed", not r["decision"].goal,
          r["decision"].reason[:90])

    # ---- 5. sarcasm and venting stay inert ------------------------------
    n_jobs, n_sent = len(fake.jobs), len(sent)
    a.hear("Oh great, ANOTHER Monday standup, exactly what my life was "
           "missing.", may_say=say_yes)
    a.hear("I swear I'm going to lose it if the wifi drops one more time.",
           may_say=say_yes)
    check("sarcasm/venting: no cards, no texts",
          len(fake.jobs) == n_jobs and len(sent) == n_sent)

    # ---- 6. cancelling over SMS kills the plan --------------------------
    a.hear("Actually you know what, let's scrap the Earls thing, "
           "he had to cancel on me.", may_say=say_yes)
    live = [j for j in fake.jobs
            if j["status"] in ("awaiting_confirm", "queued")
            and "earls" in j["goal"].lower()]
    check("an overheard cancellation kills the live dinner job",
          len(live) == 0, f"{[(j['status'], j['goal']) for j in fake.jobs]}")

    good = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\nlived-in battery: {good}/{len(CHECKS)} checks passed")
    sys.exit(0 if good == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
