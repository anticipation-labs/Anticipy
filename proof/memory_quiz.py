"""Does she actually KNOW him after hearing his days? A quiz, not a claim.

Feeds several simulated days of raw overheard lines into the real Memory,
runs the real consolidation pass (live model), then asks the questions a
personal assistant must be able to answer — and checks the profile + recall
carry the right facts to the top.

Run:  PYTHONPATH=. python3 proof/memory_quiz.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.llm import LLM  # noqa: E402
from brain.memory import Memory  # noqa: E402


DAYS = [
    # day 1 — who is in his life, what he's building
    [
        "Morning babe, I'll grab coffee on the way back",
        "Sarah wants to do the farmers market on Sunday again",
        "Yeah I'm still heads down building Anticipy, the assistant startup",
        "I'll send Priya the pitch deck by Thursday",
        "ugh I can never do early mornings, book me afternoon things",
    ],
    # day 2 — health, routine, a standing preference
    [
        "Gym at six with Marcus again, legs day",
        "Mom's hip surgery got scheduled for the twenty second, I need to be there",
        "Honestly Cactus Club at seven is kind of our default dinner now",
        "I switched to oat milk, dairy has been wrecking me lately",
    ],
    # day 3 — noise + a repeat (repeats should merge, noise should sink)
    [
        "where did I put the charger",
        "two zucchinis and a thing of hummus",
        "Sarah and I are thinking Tofino for her birthday in October",
        "Anticipy demo went well, investor wants a follow-up",
        "yeah 7 PM at Cactus Club works, as always",
    ],
]

QUIZ = [
    # (question words for recall, must-appear substring in the top facts)
    ("who is his partner", "sarah"),
    ("what is he building working on", "anticipy"),
    ("mom health surgery", "surgery"),
    ("where does he usually eat dinner", "cactus"),
    ("what milk does he drink", "oat"),
    ("birthday trip october", "tofino"),
]


def main() -> int:
    llm = LLM()
    if not llm.live:
        print("SKIP memory quiz — needs OPENROUTER_API_KEY (real model)")
        return 0

    m = Memory(llm=llm)
    t0 = time.time() - 3 * 86400
    for d, day in enumerate(DAYS):
        for i, line in enumerate(day):
            m.ingest(line, ts=t0 + d * 86400 + i * 600)

    # The nightly pass, run to completion like the worker would.
    totals = {"episodes": 0, "new": 0, "merged": 0}
    for _ in range(10):
        out = m.consolidate()
        if not out.get("ran"):
            print(f"consolidation pass failed: {out.get('reason')}")
            return 1
        for k in totals:
            totals[k] += out.get(k, 0)
        if not out.get("remaining"):
            break
    print(f"consolidated: {totals['episodes']} lines -> "
          f"{totals['new']} facts, {totals['merged']} merged\n")

    profile = m.profile_facts()
    print("her profile of him:")
    for f in profile:
        print(f"   [{f['importance']}] {f['fact']}")

    failures = []

    # 1. the quiz: recall must surface the right fact for each question
    print("\nthe quiz:")
    for q, need in QUIZ:
        words = set(q.lower().split())
        hits = m.recall(q, limit=5)
        blob = " ".join(h["fact"].lower() for h in hits)
        ok = need in blob
        print(f"   {'PASS' if ok else 'FAIL'}  {q!r} -> "
              f"{[h['fact'][:60] for h in hits[:3]]}")
        if not ok:
            failures.append(f"recall for {q!r} lost {need!r}")

    # 2. noise must not become identity: the grocery mumble and the lost
    #    charger are not facts worth knowing him by
    noise = [f["fact"].lower() for f in profile
             if "zucchini" in f["fact"].lower() or "charger" in f["fact"].lower()]
    if noise:
        failures.append(f"noise got distilled into the profile: {noise}")

    # 3. repetition must merge, not multiply: the Cactus Club default was
    #    said twice and must be at most one profile fact
    cactus = [f for f in profile if "cactus" in f["fact"].lower()]
    if len(cactus) > 1:
        failures.append(
            f"one habit became {len(cactus)} facts: "
            f"{[f['fact'] for f in cactus]}")

    # 4. the important thing outranks the mundane: mom's surgery must sit
    #    above the milk preference
    ranks = {"surgery": None, "oat": None}
    for i, f in enumerate(profile):
        for key in ranks:
            if key in f["fact"].lower() and ranks[key] is None:
                ranks[key] = i
    if ranks["surgery"] is not None and ranks["oat"] is not None \
            and ranks["surgery"] > ranks["oat"]:
        failures.append("mom's surgery ranked below the milk preference")

    print()
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"\nmemory quiz: {len(failures)} failures")
        return 1
    print("memory quiz: all green — she knows him")
    return 0


if __name__ == "__main__":
    def _load_env():
        p = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), ".env")
        if os.path.exists(p):
            for raw in open(p):
                raw = raw.strip()
                if raw and not raw.startswith("#") and "=" in raw:
                    k, v = raw.split("=", 1)
                    os.environ.setdefault(k, v)
    _load_env()
    sys.exit(main())
