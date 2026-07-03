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


def recall(query, k=8):
    """Read-only semantic recall ('what do you know relevant to <query>?'). Exercises the
    hybrid retriever so paraphrase recall (retrieval by MEANING) is observable end-to-end."""
    return _post("/memory/recall", {"query": query, "k": k})


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


# ── CLOUD-DEPTH cases (Anticipy HoE) — capabilities the ON-DEVICE stub store structurally
# CANNOT do, so they pass ONLY with the cloud stack on (Gemini embeddings + Neo4j graph) and
# FAIL on-device (that failure is the proof they exercise real cloud depth, not keywords). Kept
# APPEND-ONLY so the original 8 above stay byte-identical (never at risk).
CLOUD_CASES = [
    # (a) PARAPHRASE recall — retrieval by MEANING, zero keyword overlap. The stub embedder is a
    #     hashed bag-of-tokens: "allergic to penicillin" vs "what antibiotics should the doctor
    #     avoid for me" share NO tokens -> cosine ~0 -> the fact is filtered out of retrieval
    #     entirely. Gemini cloud embeddings score the paraphrase ~0.83 -> it surfaces. (Distinct
    #     from case 5, which only checks the fact was CAPTURED; this checks it's RETRIEVABLE by
    #     meaning through the live retriever.)
    {"name": "paraphrase recall — penicillin allergy by meaning (cloud embeddings)",
     "setup": ["I'm allergic to penicillin"],
     "recall": "what antibiotics should the doctor avoid for me",
     "grade_recall": lambda r: ([] if "penicillin" in json.dumps(r.get("items", [])).lower()
                                 else ["allergy not retrievable by paraphrase — on-device stub scores it ~0; needs Gemini embeddings"])},

    # (a') PARAPHRASE recall #2 — a different fact, still zero keyword overlap. On-device the
    #      regex resolver only fires on the literal word "usual"; "go-to morning drink order"
    #      needs a real embedder. Stub -> cosine 0 -> filtered; Gemini -> ~0.85 -> surfaces.
    {"name": "paraphrase recall — 'go-to morning drink' -> the oat latte (cloud embeddings)",
     "setup": ["I always get a large oat milk latte"],
     "recall": "what's my go-to morning drink order",
     "grade_recall": lambda r: ([] if any(w in json.dumps(r.get("items", [])).lower() for w in ("latte", "oat"))
                                 else ["usual order not retrievable by paraphrase — on-device stub scores it ~0; needs Gemini embeddings"])},

    # (b) MULTI-HOP graph question across 2 relationships. "my accountant is Mia" + "Jane is
    #     Mia's assistant" -> "email my accountant's assistant ..." must name JANE via the
    #     traversal Owner-[accountant]->Mia-[assistant]->Jane. The on-device store has NO graph
    #     (context.graph is None), so it can't even store the person-to-person edge, let alone
    #     traverse it — it fills only the direct accountant (Mia). Needs Neo4j.
    {"name": "multi-hop graph — my accountant's assistant -> Jane (Neo4j, 2 relationships)",
     "setup": ["my accountant is Mia Torres", "Jane Doe is Mia Torres's assistant"],
     "probe": "email my accountant's assistant the receipt",
     "grade": lambda c, d: ([] if "jane" in blob_of(c)
                            else ["did not traverse accountant->assistant to name Jane — needs the Neo4j graph (2-hop)"])},
]


def main():
    passed = 0
    all_cases = CASES + CLOUD_CASES
    print(f"MANY-CASE CONTEXT/MEMORY PROOF  ({len(all_cases)} multi-turn cases, live model)\n"
          f"  ({len(CASES)} on-device learns-you + {len(CLOUD_CASES)} cloud-depth: paraphrase recall + multi-hop graph)\n"
          + "=" * 66)
    for i, case in enumerate(all_cases, 1):
        try:
            reset()
            for line in case["setup"]:
                ingest(line); time.sleep(0.2)
            if case.get("recall") is not None:
                # cloud-depth: retrieval-by-meaning through the read-only recall surface
                fails = case["grade_recall"](recall(case["recall"]))
            else:
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
    print(f"SCORE: {passed}/{len(all_cases)}  — context memory is done at {len(all_cases)}/{len(all_cases)}")
    return passed


if __name__ == "__main__":
    main()
