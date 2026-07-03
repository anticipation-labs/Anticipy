"""final/context/never_re_ask.py — the NEVER-RE-ASK ledger (deliverable d).

The rule: before the brain asks the wearer for a slot value, check memory for a
value we already know and USE it instead of asking. Re-asking a fact you were
already told ("what's your address?" after "I live at 12 Elm St") is the single
most trust-destroying assistant failure — it proves the thing isn't listening.

This is a small, deterministic ledger over the context anchors + person book. It
does two jobs at resolve-time:

  1. known_slot(role) -> the stored value for a role the wearer named by role only
     ("book my dentist" when we already stored "my dentist is Dr. Lee").
  2. as a guard the caller consults so a clarifying ASK for a KNOWN slot is
     suppressed and filled from memory instead.

It never fabricates: an unknown slot returns None and the caller may ask once
(and, once answered, the answer is stored so it is never asked again).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# role words the wearer commonly points at without naming (we resolve them from memory)
# Deliberately excludes collision-prone verbs/objects ("email", "phone") that appear in
# ordinary task lines ("email Sam") — those must never trigger a memory fill.
_ROLE_WORDS = (
    "dentist", "doctor", "lawyer", "accountant", "landlord", "manager",
    "address", "home address", "usual order", "usual place",
    "barber", "mechanic", "vet", "pharmacy",
)


@dataclass
class SlotHit:
    slot: str
    value: str
    source: str   # "anchor" | "person"


class NeverReAskLedger:
    """Answers 'do we already know this slot?' from the stored context facts."""

    def __init__(self, memory) -> None:
        self.memory = memory

    def _facts(self) -> list[dict]:
        out: list[dict] = []
        try:
            items = self.memory.profile.all()
        except Exception:
            return out
        for it in items:
            f = getattr(it, "fields", None) or {}
            if not f.get("context_fact"):
                continue
            out.append({
                "ctype": f.get("ctype"), "key": str(f.get("ckey") or "").lower(),
                "value": str(f.get("cvalue") or getattr(it, "text", "") or ""),
                "name": str(f.get("cname") or ""), "role": str(f.get("crole") or "").lower(),
            })
        return out

    def known_slot(self, slot: str) -> Optional[SlotHit]:
        s = (slot or "").strip().lower()
        if not s:
            return None
        for fact in self._facts():
            if fact["ctype"] == "person" and fact["role"] and s in fact["role"]:
                who = fact["name"] + (f" ({fact['role']})" if fact["role"] else "")
                return SlotHit(slot=s, value=who.strip(), source="person")
            if fact["key"] and (s == fact["key"] or s in fact["key"] or fact["key"] in s):
                return SlotHit(slot=s, value=fact["value"], source="anchor")
        return None

    def known_slots_in(self, text: str) -> list[SlotHit]:
        """Every KNOWN slot the wearer referenced by role only in ``text``
        (so the caller can fill them from memory instead of re-asking)."""
        low = (text or "").lower()
        hits: list[SlotHit] = []
        seen: set[str] = set()
        for role in _ROLE_WORDS:
            if re.search(r"\b" + re.escape(role) + r"\b", low):
                hit = self.known_slot(role)
                if hit and hit.value and hit.value.lower() not in low and hit.slot not in seen:
                    hits.append(hit)
                    seen.add(hit.slot)
        return hits


__all__ = ["NeverReAskLedger", "SlotHit"]
