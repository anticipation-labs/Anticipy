"""Room 3 — the trigger model (the alarm clock; what makes it anticipatory).

Not just react to speech: also fire on TIME and on WATCHING THE OPEN-LOOP LEDGER. A tick
re-evaluates each open/waiting commitment; one whose condition is met fires EXACTLY once
(no storms). The fired trigger is run through the SAME harm-line path as a spoken event, so
a due send-commitment still ASKS and a due research-commitment ACTS. Recipe: notes/proactive_room3.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TriggerConfig:
    stale_after_s: float = 3 * 86400.0   # ELAPSED: a commitment open this long with no due-time -> nudge


class TriggerWatcher:
    """Watches the ledger against a clock. `tick(loops, now)` returns the loops that fire now,
    each at most once (idempotent via an in-memory fired-id set)."""

    def __init__(self, config: Optional[TriggerConfig] = None) -> None:
        self.cfg = config or TriggerConfig()
        self._fired = set()   # loop ids already fired this session (fire-once; no storms)

    def _due(self, loop: dict, now: float) -> bool:
        if loop.get("id") in self._fired:
            return False
        dts = loop.get("due_ts")
        if dts is not None:                                  # TIME: an explicit due-time has arrived
            try:
                return float(dts) <= now
            except (TypeError, ValueError):
                return False
        created = loop.get("created_ts")                     # ELAPSED: open too long, no due-time
        return created is not None and (now - float(created)) >= self.cfg.stale_after_s

    def tick(self, loops: List[dict], now: float) -> List[dict]:
        fired = [l for l in loops if self._due(l, now)]
        for l in fired:
            self._fired.add(l.get("id"))
        return fired

    def already_fired(self, loop_id: str) -> bool:
        return loop_id in self._fired
