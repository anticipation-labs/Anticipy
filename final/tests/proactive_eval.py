"""final/tests/proactive_eval.py — the MANY-case proof for the final proactive.

The cure for "works on one case, breaks on the next." Runs the REAL brain (live model on :8790)
against many varied, natural utterances — different people, different phrasings — and grades each
honestly. If it only worked by hardcoding, it would fail most of these. A single number comes out:
X / N. Proactive is not "done" until this is ~N/N.

Run:  ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 final/tests/proactive_eval.py
"""
import json
import os
import urllib.request

ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8790")

# Each case: a natural sentence + what SHOULD happen. Deliberately varied so nothing can be
# pattern-matched. want=[keywords that must appear in a caught task]; silent=[phrases that must
# NOT become a task (vents)]; confirm=True means a money/irreversible task must be ask/confirm.
CASES = [
    {"say": "god I'm so done with this week, I could sleep for a year",
     "want": [], "silent": ["sleep", "done"]},
    {"say": "remind me to call the plumber tomorrow morning",
     "want": ["plumber"], "silent": []},
    {"say": "send the Q3 deck to Priya, book my flight to Austin, and grab milk on the way home",
     "want": ["priya", "austin", "milk"], "silent": []},
    {"say": "honestly today sucked, back-to-back calls, oh remind me to email the landlord about the leak, anyway I'm wiped",
     "want": ["landlord"], "silent": ["wiped", "sucked"]},
    {"say": "pick up the dry cleaning and text mom happy birthday, ugh I hate mondays",
     "want": ["cleaning", "mom"], "silent": ["hate mondays"]},
    {"say": "the meeting moved to 4pm, let the team know and prep the slides before then",
     "want": ["team", "slides"], "silent": []},
    {"say": "I'm freaking out about the deadline, just make sure the report goes out by 5",
     "want": ["report"], "silent": ["freaking out"]},
    {"say": "on the way home grab bread and eggs and pick up my prescription",
     "want": ["prescription"], "silent": []},
    {"say": "renew my gym membership, it lapsed",
     "want": ["gym"], "silent": [], "confirm": True},
    {"say": "actually never mind about the dinner reservation",
     "want": [], "silent": ["dinner", "reservation"]},
    {"say": "email Sam the signed contract when you get a sec",
     "want": ["sam", "contract"], "silent": []},
    {"say": "I've got a dentist appointment Thursday at 2 across town",
     "want": ["dentist"], "silent": []},
    {"say": "can you schedule a coffee with Dana next week and cancel my Friday 1:1",
     "want": ["dana", "friday"], "silent": []},
    {"say": "ugh the wifi keeps dropping, so annoying",
     "want": [], "silent": ["wifi", "annoying"]},
    {"say": "book the conference room for 3, order lunch for six, and send the agenda out",
     "want": ["room", "lunch", "agenda"], "silent": []},
]


def ingest(text):
    req = urllib.request.Request(f"{ENGINE}/owner/ingest",
        data=json.dumps({"text": text, "execute_actions": True}).encode(),
        headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read())
    return d.get("cards") or []


def grade(case, cards):
    blob = " ".join((c.get("title") or c.get("source_text") or "") for c in cards).lower()
    dispositions = [c.get("disposition") for c in cards]
    misses = []
    for kw in case.get("want", []):
        if kw.lower() not in blob:
            misses.append(f"DROPPED '{kw}'")
    for vent in case.get("silent", []):
        if vent.lower() in blob:
            misses.append(f"ACTED ON VENT '{vent}'")
    if case.get("confirm") and cards and all(d == "do" for d in dispositions):
        misses.append("money task auto-done instead of confirm")
    return misses


def main():
    passed = 0
    print(f"MANY-CASE PROACTIVE PROOF  ({len(CASES)} varied cases, live model)\n" + "=" * 64)
    for i, case in enumerate(CASES, 1):
        try:
            cards = ingest(case["say"])
            misses = grade(case, cards)
        except Exception as e:
            misses = [f"ERROR {type(e).__name__}: {e}"]
        ok = not misses
        passed += ok
        got = ", ".join((c.get("title") or c.get("source_text") or "")[:34] for c in (cards if not isinstance(misses, str) else [])) if ok is not None else ""
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {i:2}. {case['say'][:58]}")
        if not ok:
            print(f"        → {'; '.join(misses)}")
    print("=" * 64)
    print(f"SCORE: {passed}/{len(CASES)}  — proactive is done at {len(CASES)}/{len(CASES)}")
    return passed


if __name__ == "__main__":
    main()
