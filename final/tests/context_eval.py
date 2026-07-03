"""final/tests/context_eval.py — the MANY-case proof for the final CONTEXT/MEMORY system.

The scoreboard we build the memory system toward (Phase 0 of the memory plan). Each case is
MULTI-TURN: first we TELL the assistant something (setup), then later we REFERENCE it (probe), and
we check it actually used what it knows — resolved "the usual", picked the right person, didn't
re-ask a known fact, applied a preference, handled a retraction, kept facts fresh over time.

Runs against a THROWAWAY engine (fresh temp data dir) so it never touches real memory. Reset between
cases via forget-me + the confirm phrase (safe on the throwaway).

Run:  ANTICIPY_ENGINE_URL=http://127.0.0.1:8791 python3 final/tests/context_eval.py
Context memory is "done" at ~N/N.
"""
import json
import os
import time
import urllib.request

ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8791")


def _post(path, body, timeout=90):
    req = urllib.request.Request(f"{ENGINE}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get(path, timeout=20):
    return json.loads(urllib.request.urlopen(f"{ENGINE}{path}", timeout=timeout).read())


def reset():
    for key in ("confirm", "confirm_phrase", "phrase"):
        try:
            _post("/memory/forget-me", {key: "DELETE MY DATA"}, timeout=20)
        except Exception:
            pass


def ingest(text):
    return (_post("/owner/ingest", {"text": text, "execute_actions": True}).get("cards") or [])


def blob_of(cards):
    return " ".join((c.get("title") or "") + " " + (c.get("source_text") or "") + " " +
                    (c.get("checkIn") or c.get("check_in") or "") for c in cards).lower()


def asked_about(cards, words):
    """Did it ASK a question containing any of these words (i.e. re-ask a thing it should know)?"""
    for c in cards:
        if c.get("disposition") in ("ask", "waiting") or "?" in (c.get("checkIn") or c.get("check_in") or ""):
            t = ((c.get("checkIn") or c.get("check_in") or "") + " " + (c.get("title") or "")).lower()
            if any(w in t for w in words):
                return True
    return False


# Each case: setup lines (build memory) → probe → grader(cards, drawers) -> list of failures.
CASES = [
    {"name": "never re-ask the dentist",
     "setup": ["my dentist is Dr. Lee on King Street", "her front desk number is 555-0142"],
     "probe": "book me a dentist appointment next week",
     "grade": lambda c, d: (["re-asked which dentist (it was told Dr. Lee)"] if asked_about(c, ["which", "who", "what dentist", "your dentist"]) else [])},

    {"name": "resolve 'my usual' coffee",
     "setup": ["I always get a large oat milk latte", "from the cafe on Main Street"],
     "probe": "grab my usual coffee order",
     "grade": lambda c, d: ([] if ("oat" in blob_of(c) or "latte" in blob_of(c)) else ["did not resolve 'usual' to the oat latte"])},

    {"name": "disambiguate two Sams",
     "setup": ["Sam Rivera is my lawyer", "Sam Chen is my little brother"],
     "probe": "email Sam the signed contract",
     "grade": lambda c, d: ([] if ("rivera" in blob_of(c) or "lawyer" in blob_of(c) or asked_about(c, ["which sam", "which one"])) else ["did not pick the lawyer nor ask which Sam"])},

    {"name": "fact went stale (bi-temporal)",
     "setup": ["I work at Acme Corp", "actually I just started at Globex yesterday"],
     "probe": "remind me to update my work email signature",
     "grade": lambda c, d: (["used the stale employer Acme"] if "acme" in blob_of(c) else [])},

    {"name": "surface a relevant known fact (semantic)",
     "setup": ["I'm allergic to penicillin", "I really hate going to the dentist"],
     "probe": "find me a walk-in doctor for this sinus infection",
     "grade": lambda c, d: ([] if "penicillin" in (json.dumps(d).lower()) else ["allergy not retrievable when it matters"])},

    {"name": "handle a retraction",
     "setup": ["remind me to call the bank tomorrow morning"],
     "probe": "actually never mind the bank thing",
     "grade": lambda c, d: (["retracted task still lingers as an open loop"] if "bank" in json.dumps(d.get("drawers", {}).get("open_loops", {})).lower() else [])},

    {"name": "apply a standing preference",
     "setup": ["I only take meetings in the morning", "never book me anything before 9am"],
     "probe": "set up a call with Dana this week",
     "grade": lambda c, d: ([] if ("morning" in blob_of(c) or "9" in blob_of(c) or asked_about(c, ["when", "what time"])) else ["ignored the morning-only preference"])},

    {"name": "never re-ask my address",
     "setup": ["I live at 12 Elm Street, apartment 4"],
     "probe": "order me a pizza for tonight",
     "grade": lambda c, d: (["re-asked my address (it was told 12 Elm St)"] if asked_about(c, ["address", "where", "deliver to"]) else [])},
]


def main():
    passed = 0
    print(f"MANY-CASE CONTEXT/MEMORY PROOF  ({len(CASES)} multi-turn cases, live model)\n" + "=" * 66)
    for i, case in enumerate(CASES, 1):
        try:
            reset()
            for line in case["setup"]:
                ingest(line); time.sleep(0.2)
            cards = ingest(case["probe"])
            drawers = {}
            try:
                drawers = _get("/memory/drawers")
            except Exception:
                pass
            fails = case["grade"](cards, drawers)
        except Exception as e:
            fails = [f"ERROR {type(e).__name__}: {str(e)[:60]}"]
        ok = not fails
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {i}. {case['name']}")
        if not ok:
            print(f"        → {'; '.join(fails)}")
    print("=" * 66)
    print(f"SCORE: {passed}/{len(CASES)}  — context memory is done at {len(CASES)}/{len(CASES)}")
    return passed


if __name__ == "__main__":
    main()
