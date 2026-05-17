"""Layer G: personalization. Wearer-specific shorthand ("the
Thursday thing", "my usual", "the regular sync") is ambiguous the
FIRST time it is heard (no learned mapping) and must CONFIRM; the
wearer's reply to that one confirmation teaches the mapping; every
LATER occurrence of the SAME shorthand resolves from learned memory
WITHOUT asking again.

The decision (confirm-first vs resolve-later) is driven only by
content + accumulated memory, never by the scenario label. The
learned expansion comes from the simulated wearer's reply to the
one confirmation (the sim's stand-in for the spoken answer), which
is how a real confirmation would teach it.
"""

from __future__ import annotations

import re
from typing import Optional

from app.proactive_day.world import SimWorld

_SHORTHAND_PATS = [
    (re.compile(r"\bthe (\w+) thing\b", re.I), "the_{0}_thing"),
    (re.compile(r"\bmy usual( for \w+)?\b", re.I), "my_usual"),
    (re.compile(r"\bthe regular (\w+)\b", re.I), "the_regular_{0}"),
    (re.compile(r"\bthe same as (?:always|usual)\b", re.I), "the_same"),
]


def shorthand_key(text: str) -> Optional[str]:
    """A stable key for a wearer-shorthand phrase, or None if the
    utterance carries no shorthand. Content-derived, deterministic.
    """
    low = (text or "").lower()
    for pat, tmpl in _SHORTHAND_PATS:
        m = pat.search(low)
        if m:
            grp = (m.group(1) or "").strip() if m.groups() else ""
            grp = re.sub(r"[^a-z0-9]", "", grp)
            try:
                return tmpl.format(grp) if "{0}" in tmpl else tmpl
            except Exception:
                return tmpl
    return None


def personalize(event: dict, world: SimWorld) -> tuple[str, Optional[str]]:
    """Returns one of:
      ("not_shorthand", None)         normal flow
      ("resolved", expansion_text)    learned -> resolve on expansion
      ("confirm_learn", key)          unknown -> CONFIRM, teach mapping
    The mapping is learned by writing world.facts[key] from the
    simulated wearer reply (event['expansion']) the first time.
    """
    key = shorthand_key(event.get("text", ""))
    if not key:
        return ("not_shorthand", None)
    learned = world.facts.get(key)
    if learned:
        return ("resolved", learned)
    # unknown shorthand: ask exactly once, and the wearer's reply to
    # THAT confirmation teaches the mapping for the rest of the day.
    expansion = event.get("expansion")
    if expansion:
        world.facts[key] = expansion          # learned from the reply
    return ("confirm_learn", key)
