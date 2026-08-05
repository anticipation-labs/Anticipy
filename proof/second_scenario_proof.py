"""The anti-overfitting proof: a dinner plan that shares NOTHING with Cactus.

Every dedupe threshold and regression case was tuned on the Cactus Club
conversation, so Cactus-shaped talk traverses the best-tested path — the
audit called this overfitting-by-tuning, and Omar's own live test found it:
Cactus behaved, Earl's misbehaved. This proof runs a second conversation
family — different venue, different day, LUNCH not dinner, party of four,
terser phrasing — through the identical brain with the live model. Nothing
scenario-shaped may exist in the product for this to pass; that is the point.

Run:  OPENROUTER_API_KEY=... PYTHONPATH=. python3 proof/second_scenario_proof.py
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402

JOBS: list[dict] = []


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")


def _get(url, params=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"items": []})
    filt = (params or {}).get("filter", "")
    want = [s for s in ("awaiting_confirm", "queued") if s in filt]
    return _R({"items": list(reversed([j for j in JOBS if j["status"] in want]))})


def _post(url, json=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"id": "x"})
    rec = dict(json or {})
    rec["id"] = f"job{len(JOBS) + 1}"
    JOBS.append(rec)
    return _R(rec)


def _patch(url, json=None, timeout=None, **kw):
    jid = url.rstrip("/").rsplit("/", 1)[-1]
    for j in JOBS:
        if j["id"] == jid:
            j.update(json or {})
            return _R(j)
    return _R({}, ok=False)


pb.get, pb.post, pb.patch = _get, _post, _patch

from brain.anticipy_core import Anticipy  # noqa: E402
from brain.llm import LLM  # noqa: E402
from brain.memory import Memory  # noqa: E402

# A different conversation family: terse, weekend lunch, four people, a
# venue with a location nickname — none of the Cactus wording survives here.
TRANSCRIPT = [
    "Yo are we still on for this weekend",
    "honestly let's just do Earls",
    "the one downtown or the Brooklyn one",
    "Brooklyn one for sure",
    "works say Saturday at one",
    "one o'clock yeah",
    "it'll be us four right the whole crew",
    "yeah all four of us bet see you Saturday",
]


def main() -> int:
    llm = LLM()
    if not llm.live:
        print("SKIP second scenario — no OPENROUTER_API_KEY, needs the real model")
        return 0

    a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="second-scenario")
    texts: list[str] = []
    a.notify_owner = lambda msg, channel="sms": texts.append(msg) or {"sent": True}

    convo = []
    for line in TRANSCRIPT:
        out = a.hear(line, context=list(convo[-8:]))
        convo.append(line)
        d = out["decision"]
        print(f"  heard: {line[:64]}")
        print(f"      -> {d.decision:6} addressee={d.addressee} goal={d.goal}")

    print("\n  her desk:")
    for j in JOBS:
        print(f"      [{j['status']:16}] lane={j.get('lane') or 'browser':9} {j['goal']}")

    failures = []
    held = [j for j in JOBS if j["status"] == "awaiting_confirm"]
    if len(held) != 1:
        failures.append(f"expected exactly one held booking, got {len(held)}")
    else:
        g = held[0]["goal"].lower()
        for detail, label in (("earl", "the venue"),
                              (r"saturday", "the day"),
                              (r"\b(1|one)\b|1\s?pm|1:00|13:00", "the time"),
                              (r"\b(4|four)\b", "the party size")):
            if not re.search(detail, g):
                failures.append(f"the booking lost {label}: {held[0]['goal']!r}")
    if len(JOBS) > 3:
        failures.append(f"{len(JOBS)} jobs for one lunch — duplicates")
    if len(texts) == 0:
        failures.append("silent card — he was never asked")
    elif len(texts) > 1:
        failures.append(f"{len(texts)} texts for one plan — spam: {texts}")

    print(f"\n  texts sent ({len(texts)}):")
    for t in texts:
        print(f"      {t}")

    print()
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print("\nSECOND SCENARIO: NOT READY")
        return 1
    print("PASS one held booking carrying venue + day + time + party of four")
    print("PASS no duplicate pile-up")
    print("PASS exactly one text asking his go-ahead")
    print("\nSECOND SCENARIO: READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
