"""Replay the FOURTH live silence of 2026-08-09, verbatim shape.

An agreed dinner — Earls in West Vancouver, tomorrow evening — where the
friend owns one detail: "I'll text you a time". Triage called it someone
else's job and she went inert; the feed then wore "Looking into it" over
nothing. A plan he is a PARTY to is his plan: held card, one text.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy
from brain.llm import LLM
from brain.memory import Memory


LINE = ("How is tomorrow we always get a cactus can we change it up yeah "
        "let's do the I'm not sure why don't we do the Earls in West "
        "Vancouver for sure let's do that I'll see you tomorrow evening "
        "yeah yeah I'll text you a time")


def run(n: int) -> bool:
    sent, queued = [], []
    a = Anticipy(memory=Memory(":memory:"), llm=LLM(), owner_id=f"tt{n}")
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    a._pending_jobs = lambda: []
    a._queue_job = lambda goal, params, hold=False: (
        queued.append(goal) or f"fake{n}")
    a.hear(LINE, may_say=lambda *a_, **k_: True)
    if not queued:
        print(f"  run {n}: FAIL — no card (the live inertness)")
        return False
    if not sent:
        print(f"  run {n}: FAIL — card but no text")
        return False
    print(f"  run {n}: OK — {sent[0]!r}")
    return True


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    good = sum(run(i) for i in range(rounds))
    print(f"text-you-a-time replay: {good}/{rounds} held+texted")
    sys.exit(0 if good == rounds else 1)
