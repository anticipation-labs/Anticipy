"""WHOSE JOB IS IT? A repeatable score, on the model production actually runs.

This is the oldest unsolved problem in the product and the one Omar keeps
hitting. The pendant hears ONE side, so a conversation with somebody else, a
note dictated at a machine, and a thought said out loud are the same signal:
his voice, no reply. She has to work out who the words were AIMED at and WHOSE
obligation they created, and she gets it wrong often enough to be dangerous.

Run it before and after any change to triage or the addressee lanes:

    ANTICIPY_MODEL=google/gemini-2.5-flash python3 proof/whose_job_scorecard.py

It scores, it does not assert — a number that moves is the point. Every line is
real, from his own logs or his own reports.

THE FINDING THAT MATTERS, measured 2026-08-08. The Priya line — the one that
opened Gmail on him — comes back "ignore / other" three times out of three when
judged ON ITS OWN. Triage is RIGHT about it. It only became a job once
conversation context was added around it.

So the fault is not that she cannot tell whose job it is. It is that something
in the surrounding context overrides a correct judgement. That is the same
shape as the other unexplained coupling recorded in
tests/test_no_release_notes.py, where a change downstream of triage moved
triage's own verdict. Both point at context handling, not at the prompt.
"""
import collections
import concurrent.futures as cf
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.llm import LLM  # noqa: E402
from brain.orchestrator import TRIAGE_SYSTEM, _extract_json  # noqa: E402

# (line, expected owes, why — in plain words)
CASES = [
    ("Hey how are you I'm good I'm good long time no see yeah yeah yeah yeah I "
     "can't get your deck yeah we really love your deck for sure let's do the "
     "deck I'll send it to your email",
     "owner", "he told Priya HE would send it — 2026-08-07, opened Gmail on him"),

    ("if you don't mind putting that word in with Sakib",
     "other", "he asked THEM for a favour — the investor call, 2026-08-06"),

    ("yeah I'll get that over to you by Friday",
     "owner", "a promise he made to somebody else"),

    ("can you send me the deck when you get a chance",
     "other", "he is asking the person in front of him"),

    ("let's book Cactus Club for 7pm tomorrow just the two of us",
     "owner", "a plan with nobody assigned — the thing she exists to catch"),

    ("I need to email Priya the invoice later today",
     "owner", "his own to-do, said out loud"),

    ("Anticipy can you book us dinner at 7 tomorrow at Cactus Club",
     "owner", "addressed to her by name"),

    ("she said she'd send the contract over tonight",
     "other", "somebody else's promise, reported"),

    ("Pill 491 kill 492 kill 493 of your list",
     "machine", "dictated into his laptop"),

    ("4546 4748 reply my inbox drive to Toby's email",
     "machine", "dictated into his laptop"),
]

RUNS = 3


def main() -> int:
    llm = LLM()
    if not llm.live:
        print("SKIP — no OPENROUTER_API_KEY, this needs the real model")
        return 0

    def ask(text):
        try:
            return json.loads(_extract_json(
                llm.chat(TRIAGE_SYSTEM, text, temperature=0.0).text))
        except Exception as e:
            return {"error": str(e)}

    print(f"model={llm.model}   {RUNS} runs per line\n")
    right = 0
    total = 0
    wrong_lines = []
    for line, want, why in CASES:
        with cf.ThreadPoolExecutor(max_workers=RUNS) as ex:
            outs = list(ex.map(lambda _: ask(line), range(RUNS)))
        got = collections.Counter((o.get("owes") or "?") for o in outs)
        hits = got.get(want, 0)
        right += hits
        total += RUNS
        mark = "ok  " if hits == RUNS else ("part" if hits else "MISS")
        print(f"  {mark} {hits}/{RUNS} {want:8} got={dict(got)}")
        print(f"       {why}")
        print(f"       {line[:72]}")
        if hits < RUNS:
            wrong_lines.append((line, want, dict(got)))
        print()

    pct = 100.0 * right / max(1, total)
    print(f"WHOSE-JOB SCORE: {right}/{total}  ({pct:.0f}%)")
    if wrong_lines:
        print(f"\n{len(wrong_lines)} line(s) she does not reliably get right:")
        for line, want, got in wrong_lines:
            print(f"   wanted {want:8} got {got}  {line[:56]}")
    # Scored, never asserted: this is a measurement to move, not a gate. The
    # gates are done_gate.py and the two booking proofs.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
