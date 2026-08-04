"""THE DEMO. Replays the real conversation from 2026-08-04 and proves she
catches a dinner plan made out loud with a friend.

On 2026-08-04 Omar agreed a whole dinner with someone — Cactus Club, the park
location, 7 PM tomorrow, two people — and every single line came back
"Noted — nothing needed". Nothing was queued, nothing was prepared, nothing
reached him. Three separate defects, all invisible:

  1. The ambient lane refused ALL consequential work from person-to-person
     speech, so the plan could never become a task.
  2. Word-overlap dedupe let the RESEARCH job swallow the BOOKING job, so
     even an explicit "can you book dinner" created nothing.
  3. Each turn that added a detail minted another job instead of improving
     the one already there.

This script fails if any of them come back. It uses the live model, because
the whole point is that nothing here is keyword-matched or pre-programmed —
she has to actually understand a messy, overlapping, half-transcribed
conversation and pull one clean intention out of it.

Run:  OPENROUTER_API_KEY=... PYTHONPATH=. python3 proof/dinner_demo_proof.py
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402

# ---- in-memory PocketBase: everything in brain/ runs for real -------------
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

# Exactly what the pendant heard, oldest first, as it appeared in the feed.
TRANSCRIPT = [
    "Hey we should go ahead and make a dinner reservation yeah for sure",
    "When do you wanna go here for",
    "Let's go out tomorrow",
    "OK back",
    "tomorrow 7 PM",
    "With who just the two of us OK for sure see you tomorrow",
    ("Yo how is it it's good you yeah yeah long time no see yeah for sure "
     "tomorrow we should go for dinner yeah yeah I would love it when would "
     "you like to go how about we do 7 PM tomorrow where cactus club which "
     "one the park location OK bet just a two of us sure sure see you tomorrow"),
    "Can you book dinner for 7 PM tomorrow",
]


def main() -> int:
    llm = LLM()
    if not llm.live:
        print("SKIP dinner demo — no OPENROUTER_API_KEY, needs the real model")
        return 0

    a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="dinner-demo")
    texts: list[str] = []
    a.notify_owner = lambda msg, channel="sms": texts.append(msg)

    intrusions, convo = [], []
    for line in TRANSCRIPT:
        before = len(texts)
        out = a.hear(line, context=list(convo[-8:]))
        convo.append(line)
        d = out["decision"]
        if len(texts) > before and d.addressee in ("person", "dictation"):
            intrusions.append((line, texts[-1]))
        print(f"  heard: {line[:64]}")
        print(f"      -> {d.decision:6} addressee={d.addressee} goal={d.goal}")

    print("\n  her desk:")
    for j in JOBS:
        print(f"      [{j['status']:16}] lane={j.get('lane') or 'browser':9} {j['goal']}")

    failures = []

    held = [j for j in JOBS if j["status"] == "awaiting_confirm"
            and re.search(r"book|reserv", j["goal"], re.I)]
    if len(held) != 1:
        failures.append(f"expected exactly one held booking, got {len(held)}")
    else:
        goal = held[0]["goal"].lower()
        # She must carry what the CONVERSATION said, not what one line said.
        # No keyword list gets her here — only actually following the thread.
        for detail, label in (("cactus", "the venue"),
                              ("7", "the time"),
                              ("tomorrow", "the day")):
            if detail not in goal:
                failures.append(f"the booking lost {label}: {held[0]['goal']!r}")
        params = held[0].get("params")
        if isinstance(params, str):
            params = json.loads(params or "{}")
        if (params or {}).get("lane") not in ("desk", None):
            failures.append(f"held work landed in lane {(params or {}).get('lane')!r}")

    if len(JOBS) > 3:
        failures.append(f"{len(JOBS)} jobs for one dinner — duplicates are back")

    if intrusions:
        failures.append(f"{len(intrusions)} texts fired on speech not aimed at her")

    print()
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print("\nDINNER DEMO: NOT READY")
        return 1
    print("PASS one held booking, carrying venue + time + day from the conversation")
    print("PASS no duplicate pile-up")
    print("PASS she never spoke over speech that wasn't aimed at her")
    print("\nDINNER DEMO: READY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
