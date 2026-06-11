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
    each at most once — within a session via the in-memory fired-id set, and ACROSS engine
    restarts via the durable `fired_at` stamp the loop record carries (ledger D16: a restart
    must never re-fire an already-fired loop — no duplicate reminder sends, no duplicate
    pipeline re-entry)."""

    def __init__(self, config: Optional[TriggerConfig] = None) -> None:
        self.cfg = config or TriggerConfig()
        self._fired = set()   # loop ids already fired this session (fire-once; no storms)

    def _due(self, loop: dict, now: float) -> bool:
        if loop.get("id") in self._fired:
            return False
        if loop.get("fired_at") is not None:   # D16: durably fired (any prior session) — never again
            return False
        for key in ("remind_ts", "due_ts"):                  # TIME: remind lead (due-15m) beats due
            ts = loop.get(key)
            if ts is not None:
                try:
                    return float(ts) <= now
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
