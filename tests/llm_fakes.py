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
    def __init__(self, consolidations=None, same_verdicts=None):
        self.consolidations = list(consolidations or [])
        self.same_verdicts = list(same_verdicts or [])
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
            verdict = (self.same_verdicts.pop(0)
                       if self.same_verdicts else False)
            return _Reply(json.dumps({"same": verdict}))
        return _Reply("{}")

    def consolidation_calls(self) -> list[str]:
        return [user for system, user in self.calls if "distill" in system]
