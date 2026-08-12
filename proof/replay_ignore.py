"""Replay the exact overheard-dinner line that production judged 'ignore'.

Runs Anticipy.hear() in-process with the live model, prints the full
decision (verdict, goal, reason, addressee, owes) and any queued jobs,
several times, to see WHERE the 'Noted, nothing needed' comes from.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for raw in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
    raw = raw.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        k, v = raw.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"'))

from brain.llm import LLM                      # noqa: E402
from brain.memory import Memory                # noqa: E402
from brain.anticipy_core import Anticipy       # noqa: E402


class FakeJobs:
    def __init__(self):
        self.jobs = []

    def post(self, url, json=None, timeout=10):
        rec = {"id": f"j{len(self.jobs)}", "goal": json["goal"],
               "params": json["params"], "status": json["status"]}
        self.jobs.append(rec)
        body = dict(rec)

        class R:
            ok = True
            def raise_for_status(self): pass
            def json(self): return body
        return R()


LINE = ("Yeah I know we should really go out for dinner yeah we totally "
        "should house tomorrow at Earl's at 2:30 in West Van yeah for sure "
        "I'd be down for that")

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 4

for i in range(RUNS):
    llm = LLM()
    mem = Memory(":memory:", llm=llm)
    a = Anticipy(memory=mem, llm=llm)
    fake = FakeJobs()
    import brain.anticipy_core as core
    core.pb.post = fake.post
    out = a.hear(LINE)
    d = out["decision"]
    print(f"\n=== run {i+1} ===")
    print("decision :", d.decision)
    print("goal     :", repr(d.goal))
    print("reason   :", repr(getattr(d, 'reason', '')))
    print("addressee:", repr(getattr(d, 'addressee', '')))
    print("owes     :", repr(getattr(d, 'owes', '')))
    print("says     :", repr(out.get("anticipy_says")))
    for j in fake.jobs:
        print("job      :", j["status"], repr(j["goal"]))
