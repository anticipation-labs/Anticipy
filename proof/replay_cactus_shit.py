"""Replay the THIRD live silence of 2026-08-09, verbatim shape.

He trashed Cactus, picked Earls West Van, and the card was built — then the
24-hour word-overlap dedupe matched it against the MORNING's dinner texts,
silenced her, and the cancel branch destroyed the card. A fresh plan must
always produce its one text, even when it rhymes with yesterday's.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy
from brain.llm import LLM
from brain.memory import Memory
from brain import worker as W


LINES = [
    "yo yo long time no see bet for sure bro",
    "we should really go out for that dinner we should really go to Cactus "
    "Cactus Cactus that place is shit I hear you let's do Earls and let's do "
    "the West Van location see you tomorrow",
]

# What she already texted him EARLIER TODAY, about a different dinner —
# the exact records that silenced the third plan live.
EARLIER = [
    {"kind": "anticipy_says", "decision": "act",
     "goal": "Book dinner at Earls in West End for tomorrow evening",
     "text": "for tomorrow's dinner at Earls West Van, what time and how many?"},
]


def run(n: int) -> bool:
    import types
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000Z")
    rows = [dict(r, created=now) for r in EARLIER]

    real_get = W.pb.get

    def fake_get(url, params=None, timeout=None, **k):
        if "anticipy_says" in (params or {}).get("filter", ""):
            return types.SimpleNamespace(ok=True,
                                         json=lambda: {"items": rows})
        return real_get(url, params=params, timeout=timeout, **k)

    W.pb.get = fake_get
    try:
        sent = []
        a = Anticipy(memory=Memory(":memory:"), llm=LLM(),
                     owner_id=f"cactus{n}")
        a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
        a._pending_jobs = lambda: []
        a._queue_job = lambda goal, params, hold=False: f"fake{n}"
        for line in LINES:
            a.hear(line, may_say=W.SPEAK_ONCE)
        if not sent:
            print(f"  run {n}: FAIL — total silence (the live bug)")
            return False
        print(f"  run {n}: OK — {sent[0]!r}")
        return True
    finally:
        W.pb.get = real_get


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    good = sum(run(i) for i in range(rounds))
    print(f"cactus-shit replay: {good}/{rounds} texted")
    sys.exit(0 if good == rounds else 1)
