"""A scripted stand-in for brain.llm.LLM, for offline consolidation tests.

Routes on the system prompt: consolidation asks get popped off a queue (so
successive nightly passes can answer differently, or raise to simulate a
crash), same-fact judgments come off their own queue, and everything else —
per-line extraction included — gets "{}" so it contributes nothing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class _Reply:
    text: str


class FakeLLM:
    """`relations` scripts the three-way verdict SAME_FACT_SYSTEM now asks for:
    "same", "replaces" or "different", popped one per judgement.

    `same_verdicts` is the older two-way sugar and still works — True is
    "same", False is "different". It cannot express "replaces", which is the
    point of the wider question, so a supersession test scripts `relations`.
    Both default to empty, and an empty queue answers "different": a fake that
    ran out of script must not start retiring facts.

    THE QUESTION IS ASKED ABOUT A LIST NOW, not a pair: the sift may no longer
    decide which stored notes reach the model, so every live note goes in one
    call and the reply names one of them by "n". A scripted verdict therefore
    answers about `stored_notes[0]` — the note the sift ORDERED first — which
    is the same note the old pairwise loop would have asked about first.
    `answer_n` overrides that when a test needs the verdict pinned to a
    different note in the list.
    """

    def __init__(self, consolidations=None, same_verdicts=None,
                 relations=None, answer_n=None):
        self.consolidations = list(consolidations or [])
        self.same_verdicts = list(same_verdicts or [])
        self.relations = list(relations or [])
        self.answer_n = answer_n
        self.calls: list[tuple[str, str]] = []

    # **kw, not a pinned signature: brain.llm.LLM.chat grew an `aux` flag
    # for the mechanical calls, and a double that refuses unknown keywords
    # turns that into a TypeError swallowed by the caller's try/except —
    # the dedup silently stopped happening and the test said `0 == 1`.
    def chat(self, system: str, user: str, temperature: float = 0.1, **kw) -> _Reply:
        self.calls.append((system, user))
        if "distill" in system:
            payload = (self.consolidations.pop(0)
                       if self.consolidations else {"facts": []})
            if isinstance(payload, Exception):
                raise payload
            return _Reply(json.dumps(payload))
        if "SAME underlying fact" in system:
            if self.relations:
                relation = self.relations.pop(0)
            elif self.same_verdicts:
                relation = "same" if self.same_verdicts.pop(0) else "different"
            else:
                relation = "different"
            if relation == "different":
                return _Reply(json.dumps({"n": None, "relation": relation}))
            # Which stored note the verdict is about. Read off the payload
            # rather than assumed, so a scripted verdict cannot silently
            # answer about a note the store never offered.
            try:
                notes = json.loads(user).get("stored_notes") or []
            except Exception:
                notes = []
            n = self.answer_n if self.answer_n is not None else 1
            if not notes or not 1 <= n <= len(notes):
                return _Reply(json.dumps({"n": None, "relation": "different"}))
            return _Reply(json.dumps({"n": n, "relation": relation}))
        return _Reply("{}")

    def relation_calls(self) -> list[str]:
        """Every pair actually put to the model. The supersession bug was that
        the pair the feature exists for never reached it at all, so a test that
        only checks the outcome can pass while the sift is still silently
        excluding the case."""
        return [user for system, user in self.calls
                if "SAME underlying fact" in system]

    def consolidation_calls(self) -> list[str]:
        return [user for system, user in self.calls if "distill" in system]


# --------------------------------------------------------------------------
# THE CLOCK'S SECOND QUESTION
# --------------------------------------------------------------------------
# clock_tick() no longer decides whether a remembered sentence expressed an
# obligation by reading its verbs — `_CLOCK_ACTION_SOURCE_RE` was Law-1 audit
# item 11 and is gone. It puts the question to a model instead
# (orchestrator.work_is_licensed) and compares the verdict.
#
# That means a clock double whose `chat` answers EVERY system prompt with its
# one canned reply now says nothing this code can read when asked the licence
# question — LICENCE_UNANSWERED, which refuses, because an authority floor
# with no verdict has no authority. Route on the prompt, the way FakeLLM
# already does, and the double stays honest about which question it answered.
LICENCE_KEY = "licenses_work"


def licence_reply(system: str, licensed: bool = True):
    """The JSON a stand-in should answer the licence question with, or None
    when `system` is some other prompt and the caller should carry on.

    `licensed=False` is how a test says "the model read his words and found
    no errand of his in them" without going anywhere near a verb list."""
    if LICENCE_KEY not in (system or ""):
        return None
    return json.dumps({LICENCE_KEY: bool(licensed)})
