"""Replay the 2026-08-09 live failure verbatim against the real model.

He said, out loud, with a friend — explicitly NOT knowing the time:
the text must ask for the time (or say the plan without one), must never
invent a time, and must never claim a reservation exists.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy
from brain.llm import LLM
from brain.memory import Memory


LINES = [
    "Hey hey hey how are you I'm good I'm good yourself yeah I'm great",
    "how was that show damn that show was good damn it was so good",
    "oh okay wait sorry just hold on for a second hey secretary sorry I just "
    "can't deal with this right now can you handle it oh yeah no problem",
    "Oh shit there's a problem OK OK thank you yeah OK bro we really gotta go "
    "for dinner yeah I don't know when though my schedule looks a little free "
    "tomorrow evening yeah OK let's grab dinner at the Earls West Van yeah "
    "the Earls West van is great OK let's do it",
]


def run(n: int) -> bool:
    sent = []
    a = Anticipy(memory=Memory(":memory:"), llm=LLM(), owner_id=f"replay{n}")
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    a._pending_jobs = lambda: []
    a._queue_job = lambda goal, params, hold=False: f"fake{n}"
    for line in LINES:
        a.hear(line, may_say=lambda *a_, **k_: True)
    ok = True
    if not sent:
        print(f"  run {n}: FAIL — total silence")
        return False
    for t in sent:
        low = t.lower()
        if re.search(r"\b7\b|7\s*p\.?m|seven", low):
            print(f"  run {n}: FAIL — invented a time: {t!r}")
            ok = False
        # A CLAIM of a result — "i booked it", "table's reserved", "got you
        # a table" — not the word appearing inside an honest denial
        # ("nothing gets booked until you say").
        if re.search(r"\bgot (you )?a? ?(reservation|table)|"
                     r"\b(i|i've|it's|its|is|was|are)\s+(been\s+)?"
                     r"(booked|reserved)\b", low):
            print(f"  run {n}: FAIL — claimed a result: {t!r}")
            ok = False
    if ok:
        print(f"  run {n}: OK — {sent[0]!r}")
    return ok


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    good = sum(run(i) for i in range(rounds))
    print(f"earls replay: {good}/{rounds} clean")
    sys.exit(0 if good == rounds else 1)
