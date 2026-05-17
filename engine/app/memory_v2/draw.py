"""MH-P3: the retrieval / draw path into the resolution engine.

The resolution engine (proactive_day.resolve) already resolves a
load-bearing reference against the wearer's live world OR routes to
CONFIRM. This adds ONE safe source of additional resolving power: a
durable, wearer-confirmed fact already in the memory store. It NEVER
guesses; it only supplies a referent when a high-trust durable fact
deterministically matches the reference.

Safety / no context-rot (the hard constraint):
  - The draw is consulted ONLY for an utterance the FROZEN engine
    already accepted as an instruction (the pipeline calls it after
    the frozen gate). Chatter is IGNOREd upstream and never reaches
    the draw, so retrieved memory cannot turn ambient talk into an
    action: chatter false-action stays <= 0.02.
  - Only DURABLE, wearer-confirmed/promoted facts are eligible
    (life_log is excluded by construction, MH-P2 invariant). A
    low-trust memory can never supply an action referent.
  - Precision over recall: at most ONE alias hit per reference, and
    only on an exact normalized alias match or a durable-fact
    embedding match >= DRAW_TAU. Ambiguity (two durable hits) ->
    supply nothing -> the resolver CONFIRMs, never guesses.

Hard latency budget: DRAW_BUDGET_MS, enforced and measured. The
production store is Supabase pgvector + the anticipy_memory_topk
RPC (wired, the labelled real edge); the gate uses the same
interface over the InProcess backend so the budget is exact.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

from app.memory_v2.write import DURABLE_KINDS, canonical_key

DRAW_TAU = 0.84
DRAW_BUDGET_MS = 25.0           # hard per-draw retrieval budget
_ALIAS_KINDS = ("preference", "habit", "fact", "contact")

_REF = re.compile(r"\b(the usual|my usual|the regular|the same as "
                  r"(?:always|usual)|the (\w+) thing)\b", re.I)


@dataclass
class DrawResult:
    object_hint: Optional[str] = None
    person_hint: Optional[str] = None
    source_key: Optional[str] = None
    latency_ms: float = 0.0
    within_budget: bool = True
    hits: int = 0


def _norm(s: str) -> str:
    return " ".join(sorted(set(re.findall(r"[a-z0-9]+", (s or "").lower()))))


async def draw(user_id: str, utterance: str, writer,
               k: int = 8) -> DrawResult:
    """Resolve an alias-style reference in `utterance` to a durable
    wearer fact, or return nothing. `writer` is the MH-P2
    MemoryWriter (its durable_facts is the invariant boundary:
    life_log is already excluded). Deterministic; latency measured
    and budget-enforced.
    """
    t0 = time.perf_counter()
    res = DrawResult()
    m = _REF.search(utterance or "")
    if not m:
        res.latency_ms = (time.perf_counter() - t0) * 1000.0
        return res

    durable = await writer.durable_facts(user_id)
    durable = [d for d in durable if d.kind in DURABLE_KINDS]
    surface = m.group(0).lower().strip()
    canon = canonical_key(surface)

    exact = [d for d in durable
             if d.value.get("alias", "").lower().strip() == surface
             or _norm(d.value.get("alias", "")) == canon]
    cands = exact
    if not cands:
        # embedding match on the alias field only (precision: an
        # alias, never the whole memory blob)
        aliased = [d for d in durable if d.value.get("alias")]
        if aliased:
            from app.memory_v2.write import _cos, _local_embed

            E = _local_embed([surface] + [d.value["alias"]
                                          for d in aliased])
            q = E[0]
            cands = [aliased[i] for i in range(len(aliased))
                     if _cos(q, E[i + 1]) >= DRAW_TAU]

    # precision over recall: exactly one durable hit, else nothing
    if len(cands) == 1:
        d = cands[0]
        val = d.value.get("resolves_to") or d.value.get("text")
        if d.kind == "contact":
            res.person_hint = val
        else:
            res.object_hint = val
        res.source_key = d.key
        res.hits = 1

    res.latency_ms = (time.perf_counter() - t0) * 1000.0
    res.within_budget = res.latency_ms <= DRAW_BUDGET_MS
    return res
