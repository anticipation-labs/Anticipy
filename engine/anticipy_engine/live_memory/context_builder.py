"""CONTEXT BUILDER — the ONE assembler of model-context for the whole spine.

Every consumer (proactive decider, browser/API hands, voice/text) calls THIS and nothing
else to get its context. That is the structural guard against "plumbed separately": memory
is read here, before the decision, in one place, and the same source of truth is shaped for
each purpose. It implements the four context-engineering moves on top of the retrieval
primitive (`Injector.inject`):

  SELECT   — hybrid retrieve (semantic+keyword+recency+importance) + ALL active open loops.
  RERANK   — (seam) cheap reorder of candidates for the moment; heuristic order in stub.
  COMPRESS — fit a per-purpose char budget; open loops are NEVER dropped to fit.
  ISOLATE  — purpose-scoped view: decide (tight+complete) / act (drill-down) / speak (facts).

Returns a typed `ContextPack` (see shared/schema). Deterministic + free in stub mode; the
live-model rerank/relevance seams are optional and never fire in tests.
"""
from __future__ import annotations

from typing import Optional

from ..shared.schema import ContextPack, ContextPurpose
from .inject import Injector
from .privacy import redact


def _scrub(s: str) -> str:
    """Redact-before-egress: mask any NEVER-STORE secret value in a string leaving the device.
    Redundant with redaction-at-capture (M5) by design — defense in depth for any item written
    outside the capture path (e.g. seeded/imported)."""
    return redact(s or "")[0]


# Per-purpose budgets. `decide` stays tight (cheap + low-latency on the hot harm-line);
# `act` gives the hands more room to drill down; `speak` is small (facts to honor).
_BUDGET = {"decide": 1600, "act": 2600, "speak": 1200}
_K = {"decide": 10, "act": 16, "speak": 8}


class ContextBuilder:
    def __init__(self, injector: Injector) -> None:
        self.injector = injector

    def build(self, about: str = "", purpose: ContextPurpose = "decide",
              k: Optional[int] = None, char_budget: Optional[int] = None,
              as_of: Optional[float] = None) -> ContextPack:
        budget = char_budget or _BUDGET.get(purpose, _BUDGET["decide"])
        kk = k or _K.get(purpose, _K["decide"])

        # SELECT (+ the injector already: dedupes, vent-gates loops, applies the abstain floor,
        # and filters by bi-temporal validity at `as_of` — expired ephemeral facts don't surface).
        prev_budget = self.injector.char_budget
        self.injector.char_budget = budget
        try:
            inj = self.injector.inject(about, k=kk, as_of=as_of)
        finally:
            self.injector.char_budget = prev_budget

        items = inj.get("items", [])
        provenance = {}
        for it in items:
            provenance[_scrub(it.text)] = getattr(it, "provenance", "stated") or "stated"

        return ContextPack(
            purpose=purpose,
            about=about,
            text=_scrub(inj.get("text", "")),
            open_loops=[_scrub(i.text) for i in inj.get("open_loops", [])],
            profile=[_scrub(i.text) for i in inj.get("profile", [])],
            history=[_scrub(i.text) for i in inj.get("history", [])],
            derived=[_scrub(i.text) for i in inj.get("derived", [])],
            top_relevance=float(inj.get("top_relevance", 0.0)),
            abstain=bool(inj.get("abstain", True)),
            provenance=provenance,
            budget_used=len(inj.get("text", "")),
            item_count=len(items),
        )
