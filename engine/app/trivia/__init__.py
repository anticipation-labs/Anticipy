"""Anticipy trivia-fire subsystem.

Smallest Anticipy moment: someone says ``wait, when did the Roman
Empire fall`` and within ~2 seconds the Mac speaks the answer through
TTS and the popover receives a fire it can render. See
``planning/07-trivia-fire/DESIGN.md`` for the architecture.

Public entry point:

    from app.trivia import maybe_fire

    record = maybe_fire(utterance)
    if record is not None:
        # trigger fired; record contains trigger + answer + delivery
        ...

The hot path integration lives in ``app.product.server._process_utterance``;
that function calls ``maybe_fire`` before the normal action pipeline so
trivia branches off without disturbing existing behavior.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from . import answer, cache, deliver, trigger


def maybe_fire(utterance: str,
               *,
               threshold: Optional[float] = None,
               deadline_s: float = 1.8,
               voice: Optional[str] = None,
               rate: Optional[int] = None) -> Optional[dict]:
    """Run the trivia path against ``utterance``.

    Returns None if the trigger does not fire. Returns a dict with
    ``trigger``, ``answer``, ``delivery``, and ``total_latency_ms`` if
    it does.
    """
    if not utterance or not utterance.strip():
        return None
    received_at = time.time()
    tr = trigger.classify(utterance, threshold=threshold)
    if not tr.fire:
        return None
    # Ensure the cache is seeded on first use. Cheap idempotent.
    try:
        cache.ensure_seeded()
    except Exception:
        pass
    ans = answer.fetch(utterance, deadline_s=deadline_s)
    delivery = deliver.deliver(
        utterance,
        ans,
        trigger_result=tr.to_dict(),
        voice=voice,
        rate=rate,
        received_at=received_at,
    )
    total_ms = round((time.time() - received_at) * 1000.0, 2)
    return {
        "trigger": tr.to_dict(),
        "answer": ans,
        "delivery": delivery,
        "received_at": received_at,
        "total_latency_ms": total_ms,
    }


def recent_fires(limit: int = 10) -> list[dict]:
    """Pass-through to ``deliver.recent_fires`` for callers that only
    need the recent log."""
    return deliver.recent_fires(limit=limit)


__all__ = [
    "answer",
    "cache",
    "deliver",
    "maybe_fire",
    "recent_fires",
    "trigger",
]
