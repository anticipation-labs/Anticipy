"""Replay the 2026-08-11 21:11-21:21 conversation disaster on the live
production model, turn by turn, against the updated classifier prompt.

Four turns, each 3x:
  1. "Do you wanna finish the girls" with a blocked earls booking -> must be
     a confirm/answer of that item, never a decline.
  2. "Let's do Earl's tomorrow at 2 PM" with a pending (misheard) rose plan
     -> must land ON the rose item with earls in changes, not fork.
  3. "I told you to book Earl's dammit" with only the rose item pending ->
     decline of rose AND a redo naming earls.
  4. "Why are you not booking" with an earls run failed minutes ago and
     nothing pending -> the reply must name the failure, never claim there
     are no active requests.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.conversation import REPLY_SYSTEM  # noqa: E402
from brain.llm import LLM  # noqa: E402


def parse(text):
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    return json.loads(m.group(0)) if m else {}


def run(llm, payload):
    return parse(llm.chat(REPLY_SYSTEM, json.dumps(payload),
                          temperature=0.0).text)


def main():
    llm = LLM()
    assert llm.live, "need OPENROUTER_API_KEY"
    results = []

    # 1. finishing is not cancelling
    p1 = {"thread": [
            {"who": "anticipy", "text": "I'm nearly through Book dinner for "
             "tomorrow at Earls in West Vancouver — I need the verification "
             "code sent to your phone to confirm the booking."},
            {"who": "owner", "text": "Hi"}, {"who": "anticipy", "text": "hey there"}],
          "pending": [],
          "blocked": [{"id": "j9", "goal": "Book dinner for tomorrow at "
                       "Earls in West Vancouver",
                       "needs": "the verification code sent to the owner's phone"}],
          "memory": [], "recent_outcomes": [],
          "owner_text": "Do you wanna finish the girls"}
    ok = 0
    for _ in range(3):
        out = run(llm, p1)
        if out.get("intent") != "decline":
            ok += 1
    results.append(("'finish the girls' never scraps the parked booking", ok))

    # 2. redirect supersedes, never forks
    p2 = {"thread": [
            {"who": "anticipy", "text": "i'm holding a dinner reservation "
             "for two at rose in west van tomorrow. what time should i make "
             "it for?"}],
          "pending": [{"id": "r1", "goal": "Book dinner for 2 at Rose in "
                       "West Vancouver tomorrow evening",
                       "status": "awaiting_confirm", "params": ""}],
          "blocked": [], "memory": [], "recent_outcomes": [],
          "owner_text": "Let's do Earl's tomorrow at 2 PM"}
    ok = 0
    for _ in range(3):
        out = run(llm, p2)
        ids = out.get("pending_ids") or [out.get("pending_id")]
        ch = json.dumps(out.get("changes") or {}).lower()
        if out.get("intent") in ("confirm", "modify", "answer") \
                and "r1" in ids and "earl" in ch:
            ok += 1
    results.append(("redirect lands ON the rose item with earls in changes", ok))

    # 3. wrong-thing correction carries a redo
    p3 = {"thread": [
            {"who": "anticipy", "text": "on it, booking rose in west van "
             "for 2 people tomorrow evening."},
            {"who": "anticipy", "text": "opentable's top result for rose in "
             "west vancouver is rose west hollywood. should i try a "
             "different search term?"}],
          "pending": [],
          "blocked": [{"id": "r1", "goal": "Book dinner for 2 at Rose in "
                       "West Vancouver tomorrow evening",
                       "needs": "a different search term or another site"}],
          "memory": [], "recent_outcomes": [],
          "owner_text": "I told you to book Earl's dammit"}
    ok = 0
    for _ in range(3):
        out = run(llm, p3)
        redo = (out.get("redo") or "").lower()
        if out.get("intent") == "decline" and "earl" in redo:
            ok += 1
    results.append(("'I told you to book Earls' declines rose AND redoes earls", ok))

    # 4. recent outcomes answer "why are you not booking"
    p4 = {"thread": [
            {"who": "owner", "text": "Good"},
            {"who": "anticipy", "text": "glad we're on the same page."}],
          "pending": [], "blocked": [], "memory": [],
          "recent_outcomes": [
            {"goal": "Book lunch at Earl's for tomorrow at 2 PM for 3 people",
             "status": "failed",
             "outcome": "max steps reached at the checkout form"},
            {"goal": "Book dinner for 2 at Rose in West Vancouver",
             "status": "cancelled", "outcome": "cancelled by owner"}],
          "owner_text": "Why are you not booking"}
    ok = 0
    for _ in range(3):
        out = run(llm, p4)
        reply = (out.get("reply") or "").lower()
        redo = (out.get("redo") or "").lower()
        truthful = ("fail" in reply or "couldn't" in reply or "stuck" in reply
                    or "didn't" in reply or "went wrong" in reply)
        no_lie = "no active" not in reply and "aren't any active" not in reply
        if truthful and no_lie and ("earl" in reply or "earl" in redo):
            ok += 1
    results.append(("'why are you not booking' answers with the failure", ok))

    bad = [r for r in results if r[1] < 3]
    for name, n in results:
        print(f"  {'ok  ' if n == 3 else 'FAIL'} {name} — {n}/3")
    print(f"operator teardown replay: {sum(1 for r in results if r[1] == 3)}/{len(results)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
