"""Room 2.6 — the breath: ambient money-transfer commands wait out the retraction.

People blurt payment commands and take them back one breath later ("Just venmo
Raj for the team dinner" ... "Hold on, he said he'd expense it. Leave it.").
Surfacing the ask on the first line interrupts the user for a commitment they
un-made seconds after making it. So a money TRANSFER command heard in AMBIENT
speech is HELD, not asked: the goal is persisted waiting (never executed), and
the terminal money block lands only if it survives a short window with no retraction.

Scope is deliberately narrow — two conditions, both required:
  - harm-line category "money" OR "binding_send", AND the text uses a TRANSFER
    verb (pay/venmo/zelle/wire/transfer/...). Direct pay-someone commands are
    the class people retract mid-conversation; buy/cart/purchase intents hit the
    terminal money wall immediately. binding_send is
    included because "send <person> <amount> over <rail>" reads as a send to
    the harm-line while being a money transfer in substance (ledger F9 —
    category jitter was bypassing this window); the rail-verb requirement
    keeps ordinary sends ("send her the lease") asking immediately.
  - the event is AMBIENT (meta.observed_at present — transcript/pendant
    capture). A typed or API command is deliberate; it hits the money wall
    immediately (SideDoor and the gate's typed money probe are unchanged).

One-way safety: a held command can only be CANCELLED (silence; money fails
toward silence, never act) or BLOCKED. It can never become an ACT or an
approval ask, and the paused goal never executes while held.

This class is pure bookkeeping + predicates: no I/O, no model calls, fully
deterministic — identical behavior at stub and live tier. The engine
(core/proactive.py) does the goal/channel/glassbox work.
"""
from __future__ import annotations

import re
from typing import List, Optional

# Direct money-movement verbs only. NOT buy/purchase/order/checkout: those are
# shopping intents, not person-to-person transfers, and their asks must surface.
_TRANSFER = re.compile(
    r"\b(?:pay|pays|paying|venmo|venmos|venmoing|zelle|zelles|paypal|"
    r"wire|wires|wiring|transfer|transfers|transferring|"
    r"reimburse|reimburses|reimbursing|donate|donates|donating)\b"
)

# Conservative spoken-retraction idioms. Verb-anchored where a negation could
# be about anything ("do NOT put the dinosaur in the sauce" must not cancel).
_RETRACTION = re.compile(
    r"\b(?:never ?mind|scratch that|forget (?:it|that)|cancel that|skip it|"
    r"hold off|we'?re (?:even|square)|park it|do nothing|"
    r"leave (?:it|that|the (?:payment|bill|invoice|tab|tip)))\b"
    r"|\b(?:don'?t|do not)\s+(?:pay|send|wire|transfer|venmo|zelle|buy|order|touch|spend)\b"
    r"|\bwait,?\s+no\b"
)


class AskDebounce:
    """Holds money-transfer asks from ambient speech for a short retraction window."""

    def __init__(self, hold_events: int = 2, hold_seconds: float = 240.0) -> None:
        self.hold_events = hold_events
        self.hold_seconds = hold_seconds
        self.held: List[dict] = []   # {goal_id, action, reason, category, held_at, events_seen}

    # ---- predicates ----

    @staticmethod
    def should_hold(text: str, category: str, meta: Optional[dict]) -> bool:
        # binding_send counts only because the rail check below makes it a money
        # transfer in substance (F9); any other category asks immediately
        if category not in ("money", "binding_send"):
            return False
        if not (meta or {}).get("observed_at"):
            return False         # typed/API command -> deliberate -> ask immediately
        return bool(_TRANSFER.search((text or "").lower()))

    @staticmethod
    def is_retraction(text: str) -> bool:
        return bool(_RETRACTION.search((text or "").lower()))

    # ---- bookkeeping (engine does the I/O) ----

    def has_held(self) -> bool:
        return bool(self.held)

    def hold(self, goal_id: str, action: str, reason: str, category: str, now: float) -> dict:
        entry = {"goal_id": goal_id, "action": action, "reason": reason,
                 "category": category, "held_at": now, "events_seen": 0}
        self.held.append(entry)
        return entry

    def cancel_on_retraction(self, text: str, now: float) -> List[dict]:
        """A retraction within the window kills the most recent held ask (people
        take back the thing they just said). Returns the cancelled entries."""
        if not self.held or not self.is_retraction(text):
            return []
        newest = self.held.pop()
        return [newest]

    def event_passed(self, now: float) -> List[dict]:
        """Count one more utterance against every held ask; pop and return the
        ones whose window is exhausted (the caller flushes them as real asks)."""
        expired = []
        survivors = []
        for h in self.held:
            h["events_seen"] += 1
            if h["events_seen"] >= self.hold_events or (now - h["held_at"]) >= self.hold_seconds:
                expired.append(h)
            else:
                survivors.append(h)
        self.held = survivors
        return expired

    def due(self, now: float) -> List[dict]:
        """Time-based flush (called from the trigger tick): the stream went
        quiet, so a surviving held ask goes out without waiting for more lines."""
        expired = [h for h in self.held if (now - h["held_at"]) >= self.hold_seconds]
        self.held = [h for h in self.held if h not in expired]
        return expired
