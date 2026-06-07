"""Room 5 — the annoyance budget (wearable 365 days).

An interruption is a withdrawal from a finite daily account, not a deposit: proactive agents
hit a hard ceiling of ~3-5 notifications/day before users take the pendant off. This caps
PROACTIVE interruptions (asks the ENGINE initiates), learns from declines (don't re-propose a
declined action-type), and prefers SUPPRESSING over deferring. USER-initiated asks are never
suppressed. The cap NUMBER is Omar's (DECISIONS-ONLY-OMAR) — configurable, default anchored to
the research 3-5/day ceiling. Recipe + sources: notes/proactive_room5.md.
"""
from __future__ import annotations

import re
from typing import List, Optional, Set

_STOP = {"the", "a", "an", "to", "of", "for", "and", "or", "my", "me", "us", "it", "this",
         "that", "about", "on", "in", "with", "your", "his", "her", "their", "our"}
_TOK = re.compile(r"[a-z0-9]+")


def _signature(action: str, category: str) -> str:
    """A general action-TYPE signature: harm category + salient content tokens."""
    toks = sorted(t for t in _TOK.findall((action or "").lower()) if len(t) >= 4 and t not in _STOP)
    return category + "|" + " ".join(toks)


class AnnoyanceBudget:
    def __init__(self, max_per_day: int = 5, window_s: float = 86400.0) -> None:
        self.max_per_day = max_per_day          # DECISIONS-ONLY-OMAR (research ceiling ~3-5/day)
        self.window_s = window_s
        self._interruptions: List[float] = []   # timestamps of proactive asks sent
        self._declined: Set[str] = set()        # action-type signatures the user has declined

    def count(self, now: float) -> int:
        return sum(1 for t in self._interruptions if now - t < self.window_s)

    def suppressed(self, action: str, category: str, now: float) -> Optional[str]:
        """Reason to suppress a PROACTIVE interruption, or None to allow it through."""
        if _signature(action, category) in self._declined:
            return "declined-type (user said no before)"
        if self.count(now) >= self.max_per_day:
            return f"over interruption budget ({self.max_per_day}/day)"
        return None

    def record_interruption(self, now: float) -> None:
        self._interruptions.append(now)

    def record_decline(self, action: str, category: str) -> None:
        self._declined.add(_signature(action, category))

    def declined_count(self) -> int:
        return len(self._declined)
