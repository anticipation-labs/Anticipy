"""Label Omar's real transcript lines with what SHOULD have happened.

The scorecard has to exist before any fix, or "better" is just a feeling.
Each line gets one expected lane:

  silent  — remember it, do nothing, say nothing. Machine dictation, someone
            else's errand, chatter, unintelligible ASR mush.
  quiet   — do the read-only work in the background; he never has to ask.
  desk    — prepare something consequential and hold it for his OK.
  text    — worth interrupting him for.

The rubric is deliberately written around WHOSE OBLIGATION the words create,
because that — not wording — is what separates "the boss wants my deck" from
"my colleague will send theirs" from "I'm reading a list to my laptop".

Anchors: the lines Omar himself identified are hard-coded as ground truth
(they came from his own Wispr Flow history, so we KNOW they were dictation).
Everything else is labelled by the model against the rubric, twice, and
disagreements are recorded rather than hidden — an honest corpus admits
where it is unsure.

Run:  OPENROUTER_API_KEY=... PYTHONPATH=. python3 overnight/label_corpus.py dev
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.llm import LLM  # noqa: E402
from brain.orchestrator import _extract_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

RUBRIC = """You are labelling what an always-listening personal assistant
SHOULD have done with one line it overheard from its owner's day.

The owner is Omar. The assistant hears everything: him talking to people,
him talking to machines (he voice-types to his laptop constantly), him
muttering, and him talking to the assistant itself. Transcription is often
garbled.

Decide ONE label:

"silent" — remember it, do nothing, say nothing. Use when:
  * he is dictating to a machine or voice-typing (reading out lists,
    numbers, email addresses, UI instructions like "press", "reply",
    "include", "remove item 491") — the machine he is talking to is
    already doing it, so there is nothing for the assistant to do;
  * the obligation belongs to SOMEONE ELSE ("I'll send it over" said by
    the other person, not by Omar);
  * chatter, opinions, venting, jokes, thinking aloud with no commitment;
  * the transcription is too mangled to act on safely.

"quiet" — do the work in the background, read-only, tell him nothing until
  it is done. Use when there is a real question or need in HIS life that
  looking something up would serve (a place, an event, a fact he wondered
  about out loud).

"desk" — prepare something that would CHANGE HIS WORLD (a booking, a
  message, a purchase) and hold it for his approval. Use only when the
  obligation is HIS, and there is a real-world anchor: a place, a time, or
  a person.

"text" — interrupt him. Reserve for when the assistant is blocked on his
  answer about something time-critical, or he asked it something directly.

Judge by MEANING and by WHOSE JOB IT IS. Reply ONLY with compact JSON:
{"label":"silent|quiet|desk|text","whose":"omar|other|machine|nobody",
 "why":"<8 words>"}"""

# Ground truth Omar supplied himself: these exact lines came from his Wispr
# Flow dictation history, so their label is not a matter of opinion.
KNOWN_DICTATION = [
    "pill 491", "kill 492", "kill 493",
    "carson michael", "rv.help23",
    "reply my inbox drive to toby",
    "what button do i press",
    "csv with the list of emails",
    "number 11 number 12", "9495 9697",
    "eric nico", "i kill 44 sorry",
]


def anchored(text: str) -> str | None:
    t = text.lower()
    return "silent" if any(k in t for k in KNOWN_DICTATION) else None


def label_one(llm: LLM, text: str) -> dict:
    try:
        res = llm.chat(RUBRIC, text, temperature=0.0)
        got = json.loads(_extract_json(res.text))
        if got.get("label") in ("silent", "quiet", "desk", "text"):
            return got
    except Exception as e:
        return {"label": None, "whose": None, "why": f"error: {e}"}
    return {"label": None, "whose": None, "why": "unparseable"}


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "dev"
    src = os.path.join(HERE, f"corpus_{which}.json")
    rows = json.load(open(src))
    llm = LLM()
    if not llm.live:
        print("need OPENROUTER_API_KEY")
        return 1

    out = []
    for i, r in enumerate(rows):
        a = anchored(r["text"])
        if a:
            out.append({**r, "gold": a, "whose": "machine",
                        "why": "Omar's own Wispr history", "source": "anchor"})
        else:
            one = label_one(llm, r["text"])
            two = label_one(llm, r["text"])
            agree = one.get("label") == two.get("label")
            out.append({**r, "gold": one.get("label"),
                        "whose": one.get("whose"), "why": one.get("why"),
                        "source": "model", "confident": agree,
                        "second_opinion": two.get("label")})
        if (i + 1) % 25 == 0:
            print(f"  labelled {i+1}/{len(rows)}")

    dst = os.path.join(HERE, f"gold_{which}.json")
    json.dump(out, open(dst, "w"), indent=1)
    counts: dict = {}
    for r in out:
        counts[r["gold"]] = counts.get(r["gold"], 0) + 1
    unsure = sum(1 for r in out if r.get("source") == "model"
                 and not r.get("confident"))
    print(f"\n{which}: {len(out)} lines -> {dst}")
    print(f"  labels: {counts}")
    print(f"  model disagreed with itself on {unsure} "
          f"({100*unsure/max(1,len(out)):.0f}%) — these are the genuinely hard ones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
