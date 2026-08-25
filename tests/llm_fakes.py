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
    """

    def __init__(self, consolidations=None, same_verdicts=None,
                 relations=None):
        self.consolidations = list(consolidations or [])
        self.same_verdicts = list(same_verdicts or [])
        self.relations = list(relations or [])
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
            return _Reply(json.dumps({"relation": relation}))
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
